import copy
import io
import json
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

import cloudinary
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from booking.models import Booking
from properties.models import (
    Amenity, Highlight, Property, PropertyContact, PropertyFeature,
    PropertyImage, PropertyPricing,
)


class ImportPropertyDataTests(TestCase):
    def setUp(self):
        original_cloud = cloudinary.config().cloud_name
        original_secure = cloudinary.config().secure
        cloudinary.config(cloud_name="dlktscrkj", secure=True)
        self.addCleanup(cloudinary.config, cloud_name=original_cloud, secure=original_secure)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "properties.json"
        self.row = {
            "id": 99,
            "name": "Sample Retreat",
            # An existing exported slug need not match today's name.
            "slug": "original-retreat",
            "location": "Nyali, Mombasa",
            "country": "Kenya",
            "property_category": "beachfront",
            "price": "125.00",
            "description": "A coastal retreat.",
            "background_image": "https://res.cloudinary.com/dlktscrkj/image/upload/v123/retreat/cover.jpg",
            "property_images": [{
                "id": 99, "image": "https://res.cloudinary.com/dlktscrkj/image/upload/v123/retreat/bedroom.jpg",
                "category": "bedroom", "order": 0,
            }],
            "amenities": {"extras": [{"title": "WiFi", "icon": "amenities/wifi"}]},
            "highlights": [{"title": "Up to 4 Guests", "image": None}],
            "pricing_options": [{
                "id": 99, "accommodation_type": "full_apartment", "guest_type": "all",
                "stay_type": "short_term", "number_of_guests": 4, "min_nights": 1,
                "max_nights": None, "price_per_night": "125.00", "weekly_price": None,
                "includes_breakfast": False, "includes_fullboard": False,
            }],
            "features": [{"id": 99, "feature_type": "outdoor", "name": "Beach Access", "description": "Nearby beach", "icon": ""}],
            "contacts": [{"id": 99, "name": "Host", "role": "Manager", "email": "host@example.com", "phone": "", "whatsapp": ""}],
            "average_rating": None,
            "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
        }

    def run_import(self, rows=None, **options):
        rows = [self.row] if rows is None else rows
        self.path.write_text(json.dumps({"count": len(rows), "next": None, "previous": None, "results": rows}))
        output = io.StringIO()
        call_command("import_property_data", input=self.path, stdout=output, **options)
        return output.getvalue()

    @patch("cloudinary.uploader.upload_resource", side_effect=AssertionError("No media uploads expected"))
    def test_import_preserves_exported_values_and_cloudinary_references(self, upload):
        self.run_import()
        prop = Property.objects.get(slug="original-retreat")
        self.assertNotEqual(prop.pk, 99)
        self.assertEqual(prop.background_image.public_id, "retreat/cover")
        self.assertEqual(prop.background_image.version, "123")
        self.assertEqual(prop.background_image.format, "jpg")
        self.assertEqual(prop.background_image.url, self.row["background_image"])
        self.assertEqual(prop.images.get().image.url, self.row["property_images"][0]["image"])
        self.assertEqual(prop.amenities.get().category, "extras")
        self.assertFalse(prop.highlights.get().image)
        self.assertEqual(prop.pricing_options.count(), 1)
        self.assertEqual(prop.features.get().name, "Beach Access")
        self.assertEqual(prop.contacts.get().email, "host@example.com")
        upload.assert_not_called()

    def test_rerun_preserves_ids_and_bookings_when_values_change(self):
        self.run_import()
        prop = Property.objects.get()
        pricing = prop.pricing_options.get()
        booking = Booking.objects.create(
            property=prop, selected_pricing=pricing,
            full_name="Example Guest", email="guest@example.com", phone="+32470123456",
            check_in=date(2027, 1, 1), check_out=date(2027, 1, 3), total_days=2,
        )
        image_id = prop.images.get().pk
        self.row["description"] = "Updated description."
        self.row["pricing_options"][0]["price_per_night"] = "150.00"
        self.run_import()
        booking.refresh_from_db()
        self.assertEqual(Property.objects.get().pk, prop.pk)
        self.assertEqual(PropertyPricing.objects.get().pk, pricing.pk)
        self.assertEqual(PropertyImage.objects.get().pk, image_id)
        self.assertEqual(booking.selected_pricing_id, pricing.pk)
        self.assertEqual(str(booking.total_amount), "250.00")
        self.assertEqual(str(PropertyPricing.objects.get().price_per_night), "150.00")
        self.assertEqual(Property.objects.get().description, "Updated description.")

    def test_dry_run_rolls_back_new_and_updated_data(self):
        output = self.run_import(dry_run=True)
        self.assertIn("no data committed", output)
        for model in [Property, PropertyImage, PropertyPricing, Amenity, Highlight, PropertyFeature, PropertyContact]:
            self.assertEqual(model.objects.count(), 0)
        self.run_import()
        self.row["description"] = "Only a preview."
        self.row["amenities"] = {}
        self.run_import(dry_run=True)
        self.assertEqual(Property.objects.get().description, "A coastal retreat.")
        self.assertEqual(Amenity.objects.count(), 1)

    def test_invalid_later_property_does_not_partially_import(self):
        second = copy.deepcopy(self.row)
        second["slug"] = "second-retreat"
        second["pricing_options"][0]["accommodation_type"] = "villa"
        with self.assertRaisesMessage(CommandError, "accommodation_type"):
            self.run_import(rows=[self.row, second])
        self.assertEqual(Property.objects.count(), 0)

    def test_referenced_stale_pricing_rolls_back_all_updates(self):
        self.run_import()
        prop = Property.objects.get()
        pricing = prop.pricing_options.get()
        image = prop.images.get()
        Booking.objects.create(
            property=prop, selected_pricing=pricing,
            full_name="Example Guest", email="guest@example.com", phone="+32470123456",
            check_in=date(2027, 1, 1), check_out=date(2027, 1, 3), total_days=2,
        )
        self.row["description"] = "Should roll back."
        self.row["property_images"] = []
        self.row["pricing_options"] = []
        with self.assertRaisesMessage(CommandError, "entire import was rolled back"):
            self.run_import()
        prop.refresh_from_db()
        self.assertEqual(prop.description, "A coastal retreat.")
        self.assertTrue(PropertyImage.objects.filter(pk=image.pk).exists())
        self.assertTrue(PropertyPricing.objects.filter(pk=pricing.pk).exists())

    def test_missing_nested_section_is_rejected(self):
        del self.row["property_images"]
        with self.assertRaisesMessage(CommandError, "missing related data"):
            self.run_import()
        self.assertFalse(Property.objects.exists())

    def test_pagination_is_rejected(self):
        self.path.write_text(json.dumps({"count": 2, "next": "https://example.com/page2", "results": [self.row]}))
        with self.assertRaisesMessage(CommandError, "complete export"):
            call_command("import_property_data", input=self.path, stdout=io.StringIO())

    def test_existing_unrelated_properties_are_rejected(self):
        Property.objects.create(name="Unrelated Property", location="Brussels", country="Belgium", price="50.00", description="Example")
        with self.assertRaisesMessage(CommandError, "Target contains properties absent"):
            self.run_import()
        self.assertEqual(Property.objects.count(), 1)

    def test_duplicate_related_entries_are_rejected(self):
        self.row["pricing_options"] *= 2
        with self.assertRaisesMessage(CommandError, "duplicate pricing_options"):
            self.run_import()

    def test_other_cloud_is_rejected(self):
        self.row["background_image"] = "https://res.cloudinary.com/another-cloud/image/upload/cover"
        with self.assertRaisesMessage(CommandError, "CLOUDINARY_CLOUD_NAME"):
            self.run_import()

    def test_empty_sections_remove_stale_unreferenced_children(self):
        self.run_import()
        self.row["amenities"] = {}
        self.row["highlights"] = []
        self.run_import()
        self.assertEqual(Amenity.objects.count(), 0)
        self.assertEqual(Highlight.objects.count(), 0)
