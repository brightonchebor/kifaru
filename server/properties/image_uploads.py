"""Shared image validation and rollback handling for upload requests."""

import logging
from collections.abc import Mapping
from pathlib import Path

import cloudinary.uploader
from cloudinary.exceptions import Error as CloudinaryError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.exceptions import APIException


logger = logging.getLogger(__name__)
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF"}
SUPPORTED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff"}
SUPPORTED_FORMAT_NAMES = "JPG, JPEG, PNG, WebP, GIF, BMP, or TIFF"


class SupportedImageField(serializers.ImageField):
    default_error_messages = {
        "unsupported_image": (
            "Unsupported image format '{format}'. Use " + SUPPORTED_FORMAT_NAMES + "."
        ),
        "invalid_image": (
            "The image is invalid, corrupted, or unsupported. Use "
            + SUPPORTED_FORMAT_NAMES + "."
        ),
    }

    def to_internal_value(self, data):
        filename = getattr(data, "name", None)
        if filename:
            extension = Path(filename).suffix.lstrip(".").lower()
            if extension not in SUPPORTED_EXTENSIONS:
                self.fail("unsupported_image", format=extension.upper() or "unknown")
        image = super().to_internal_value(data)
        # Check the decoded format as well: renaming a file must not bypass validation.
        if image.image.format not in SUPPORTED_FORMATS:
            self.fail("unsupported_image", format=image.image.format)
        return image


class ImageUploadError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_code = "image_upload_failed"


class AtomicImageUploadMixin:
    upload_fields = ()

    def run_validation(self, data=serializers.empty):
        if isinstance(data, Mapping):
            errors = {}
            for name in data:
                values = data.getlist(name) if hasattr(data, "getlist") else data[name]
                if not isinstance(values, (list, tuple)):
                    values = [values]
                if name not in self.upload_fields and any(isinstance(value, UploadedFile) for value in values):
                    errors[name] = [
                        "Unexpected image upload field. Use " + ", ".join(self.upload_fields) + "."
                    ]
                elif (name in self.upload_fields
                      and not isinstance(self.fields[name], serializers.ListField)
                      and len(values) > 1
                      and any(isinstance(value, UploadedFile) for value in values)):
                    errors[name] = ["Only one image file may be supplied in this field."]
            if errors:
                raise serializers.ValidationError(errors)
        return super().run_validation(data)

    def save(self, **kwargs):
        self._new_uploads = []
        try:
            with transaction.atomic():
                return super().save(**kwargs)
        except Exception:
            # Database rollback does not remove files already uploaded to Cloudinary.
            for resource in self._new_uploads:
                try:
                    cloudinary.uploader.destroy(
                        resource.public_id,
                        resource_type=resource.resource_type or "image",
                        type=resource.type or "upload",
                        invalidate=True,
                    )
                except Exception:
                    logger.exception("Could not clean up a failed request's uploaded image")
            raise
        finally:
            self._new_uploads = []

    def _upload_image(self, value, field, *, index=None, **options):
        if not isinstance(value, UploadedFile):
            return value
        try:
            value.seek(0)
            resource = cloudinary.uploader.upload_resource(value, resource_type="image", **options)
        except (CloudinaryError, OSError) as exc:
            detail = ["Image upload failed. Please try again."]
            if index is not None:
                detail = {index: detail}
            raise ImageUploadError({field: detail}) from exc
        self._new_uploads.append(resource)
        return resource
