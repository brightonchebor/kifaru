"""Import the property API export without uploading media or importing test data."""

import json
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlparse

import cloudinary
from django.core.exceptions import MultipleObjectsReturned, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from properties.models import (
    Amenity, Highlight, Property, PropertyContact, PropertyFeature,
    PropertyImage, PropertyPricing,
)


DEFAULT_INPUT = Path(__file__).resolve().parents[3] / "response_1776309999567.json"
RELATED = {
    "property_images": (PropertyImage, ("category", "order")),
    "pricing_options": (
        PropertyPricing,
        ("accommodation_type", "guest_type", "stay_type", "number_of_guests",
         "min_nights", "max_nights"),
    ),
    "amenities": (Amenity, ("category", "title")),
    "highlights": (Highlight, ("title",)),
    "features": (PropertyFeature, ("feature_type", "name")),
    "contacts": (PropertyContact, ("email",)),
}


def cloudinary_reference(value):
    """Keep the resource/version/format, removing only the URL's cloud prefix."""
    if not value:
        return value
    if not isinstance(value, str):
        raise ValueError("An image reference must be a string or null.")
    parsed = urlparse(value)
    if not parsed.scheme and not parsed.netloc:
        return value
    if parsed.scheme not in ("https", "http") or parsed.hostname != "res.cloudinary.com":
        raise ValueError("Image URLs must refer to res.cloudinary.com.")
    parts = unquote(parsed.path).lstrip("/").split("/", 3)
    if len(parts) != 4 or parts[1:3] != ["image", "upload"] or not parts[3]:
        raise ValueError("Expected a Cloudinary image/upload URL.")
    configured_cloud = cloudinary.config().cloud_name
    if configured_cloud != parts[0]:
        raise ValueError(
            f"Images belong to Cloudinary cloud '{parts[0]}'; "
            "set CLOUDINARY_CLOUD_NAME to that cloud before importing."
        )
    return "/".join(parts[1:])


def validated_fields(model, row, label):
    if not isinstance(row, dict):
        raise CommandError(f"{label}: expected an object.")
    fields = {field.name: field for field in model._meta.concrete_fields
              if field.name not in {"id", "property", "created_at", "updated_at"}}
    unknown = set(row) - set(fields) - {"id"}
    if unknown:
        raise CommandError(f"{label}: unknown fields: {', '.join(sorted(unknown))}.")
    values = {key: value for key, value in row.items() if key in fields}
    try:
        for key in ("image", "background_image"):
            if key in values:
                values[key] = cloudinary_reference(values[key])
        instance = model(**values)
        instance.full_clean(
            exclude=["id", "property", "created_at", "updated_at"],
            validate_unique=False, validate_constraints=False,
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise CommandError(f"{label}: {exc}") from exc
    # Include model defaults so missing optional fields cannot retain stale values.
    return {name: getattr(instance, name) for name in fields}


def read_export(path):
    try:
        with path.open(encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise CommandError(f"Cannot read property export '{path}': {exc}") from exc
    if isinstance(payload, dict):
        rows = payload.get("results")
        if (not isinstance(rows, list) or type(payload.get("count")) is not int
                or payload["count"] != len(rows)
                or payload.get("next") is not None
                or payload.get("previous") is not None):
            raise CommandError("Expected a complete export: count must match results, with no other pages.")
    elif isinstance(payload, list):
        rows = payload
    else:
        raise CommandError("Expected an API response with results, or an array of properties.")
    if not rows:
        raise CommandError("The property export is empty.")

    prepared = []
    slugs = set()
    property_names = {field.name for field in Property._meta.concrete_fields}
    for index, row in enumerate(rows, 1):
        label = f"Property {index}"
        if not isinstance(row, dict):
            raise CommandError(f"{label}: expected an object.")
        unknown = set(row) - property_names - set(RELATED) - {"average_rating"}
        if unknown:
            raise CommandError(f"{label}: unknown fields: {', '.join(sorted(unknown))}.")
        if (not isinstance(row.get("slug"), str) or not row["slug"]
                or row["slug"] in slugs):
            raise CommandError(f"{label}: slug is missing or duplicated.")
        slugs.add(row["slug"])
        label = row["slug"]
        missing = set(RELATED) - set(row)
        if missing:
            raise CommandError(f"{label}: missing related data: {', '.join(sorted(missing))}.")
        scalar = {key: value for key, value in row.items()
                  if key in property_names and key not in {"id", "created_at", "updated_at"}}
        scalar = validated_fields(Property, scalar, label)
        if scalar["min_nights"] < 1 or scalar["prepayment_percentage"] > 100:
            raise CommandError(f"{label}: invalid minimum nights or prepayment percentage.")
        nested = {}
        for name, (model, identity) in RELATED.items():
            items = row[name]
            if name == "amenities":
                if not isinstance(items, dict):
                    raise CommandError(f"{label}.amenities: expected categories containing arrays.")
                flattened = []
                for category, entries in items.items():
                    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
                        raise CommandError(f"{label}.amenities.{category}: expected an array of objects.")
                    flattened.extend(dict(entry, category=category) for entry in entries)
                items = flattened
            if not isinstance(items, list):
                raise CommandError(f"{label}.{name}: expected an array.")
            nested[name] = []
            seen = set()
            for position, item in enumerate(items, 1):
                item_label = f"{label}.{name}[{position}]"
                values = validated_fields(model, item, item_label)
                if model is PropertyPricing:
                    if (values["min_nights"] < 1
                            or (values["max_nights"] is not None
                                and values["max_nights"] < values["min_nights"])):
                        raise CommandError(f"{item_label}: invalid range of nights.")
                    prices = [values[key] for key in ("price_per_night", "weekly_price")]
                    if all(price is None for price in prices) or any(
                        price is not None and price < 0 for price in prices
                    ):
                        raise CommandError(f"{item_label}: supply a nonnegative nightly or weekly price.")
                key = tuple(values[field] for field in identity)
                if key in seen:
                    raise CommandError(f"{item_label}: duplicate {name} entry.")
                seen.add(key)
                nested[name].append(values)
        prepared.append((scalar, nested))
    return prepared


class Command(BaseCommand):
    help = "Populate properties from the complete JSON API export; --dry-run rolls back all changes."

    def add_arguments(self, parser):
        parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to the property JSON export.")
        parser.add_argument("--database", default="default", choices=tuple(connections))
        parser.add_argument("--dry-run", action="store_true", help="Validate and try the import, then roll it back.")

    def handle(self, *args, **options):
        prepared = read_export(Path(options["input"]))
        database = options["database"]
        config = connections[database].settings_dict
        self.stdout.write(f"Target: {config['ENGINE']} database={config['NAME']} host={config.get('HOST') or 'local'}")
        totals = Counter(properties=len(prepared))
        try:
            with transaction.atomic(using=database):
                manager = Property.objects.using(database)
                existing_slugs = set(manager.select_for_update().values_list("slug", flat=True))
                extra = existing_slugs - {values["slug"] for values, _ in prepared}
                if extra:
                    raise CommandError(
                        "Target contains properties absent from the export: "
                        + ", ".join(sorted(extra))
                        + ". Select the intended new database or reconcile these properties first."
                    )
                for values, nested in prepared:
                    slug = values["slug"]
                    if slug not in existing_slugs:
                        # Preserve the exported slug instead of regenerating it from the name.
                        manager.bulk_create([Property(**values)])
                    else:
                        manager.filter(slug=slug).update(**values, updated_at=timezone.now())
                    prop = manager.get(slug=slug)
                    for name, (model, identity) in RELATED.items():
                        kept = []
                        related = model.objects.using(database)
                        for item in nested[name]:
                            lookup = {key: item[key] for key in identity}
                            defaults = {key: value for key, value in item.items() if key not in identity}
                            obj, _ = related.update_or_create(property=prop, **lookup, defaults=defaults)
                            kept.append(obj.pk)
                        related.filter(property=prop).exclude(pk__in=kept).delete()
                        totals[name] += len(kept)
                    self.stdout.write(f"  Validated/imported: {slug}")
                if options["dry_run"]:
                    transaction.set_rollback(True, using=database)
        except ProtectedError as exc:
            raise CommandError(
                "A pricing option absent from this export is referenced by an existing booking. "
                "Reconcile that pricing/booking before retrying. The entire import was rolled back."
            ) from exc
        except MultipleObjectsReturned as exc:
            raise CommandError(
                "The target contains duplicate related records. Reconcile the duplicates before retrying. "
                "The entire import was rolled back."
            ) from exc
        self.stdout.write(
            self.style.SUCCESS("Dry run passed; no data committed." if options["dry_run"] else "Import complete.")
        )
        for name, count in totals.items():
            self.stdout.write(f"  {name}: {count}")
