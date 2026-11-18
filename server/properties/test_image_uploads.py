import io
import json
from unittest.mock import call, patch

import cloudinary
from cloudinary.exceptions import Error as CloudinaryError
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase
from PIL import Image
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from properties.image_uploads import SupportedImageField
from properties.models import Amenity, Gallery, Highlight, Property, PropertyImage
from properties.views import (
    GalleryDetailView, GalleryListView, PropertyDetailView, PropertyListCreateView,
)


def image_file(name="photo.png", image_format="PNG"):
    data = io.BytesIO()
    Image.new("RGB", (32, 32), color="red").save(data, format=image_format)
    return SimpleUploadedFile(name, data.getvalue(), content_type="image/" + image_format.lower())


def avif_file():
    return SimpleUploadedFile("photo.avif", b"\x00\x00\x00\x20ftypavif", content_type="image/avif")


class ImageUploadTests(TestCase):
    def setUp(self):
        original_cloud, original_secure = cloudinary.config().cloud_name, cloudinary.config().secure
        cloudinary.config(cloud_name="upload-tests", secure=True)
        self.addCleanup(cloudinary.config, cloud_name=original_cloud, secure=original_secure)
        self.factory = APIRequestFactory()
        self.admin = get_user_model()(email="admin@example.com", is_staff=True, role="admin")
        self.resources = []
        upload_patch = patch("cloudinary.uploader.upload_resource", side_effect=self.upload_success)
        self.upload = upload_patch.start()
        self.addCleanup(upload_patch.stop)
        cleanup_patch = patch("cloudinary.uploader.destroy", return_value={"result": "ok"})
        self.cleanup = cleanup_patch.start()
        self.addCleanup(cleanup_patch.stop)
        self.payload = {
            "name": "Sample Retreat", "location": "Nyali", "country": "Kenya",
            "price": "100.00", "description": "Original description",
        }

    def upload_success(self, file, **options):
        resource = cloudinary.CloudinaryResource(
            f"new/upload-{len(self.resources)}", version="1", format="png",
            resource_type="image", type="upload",
        )
        self.resources.append(resource)
        return resource

    def request(self, view, method, data, **kwargs):
        request = getattr(self.factory, method)("/api/upload/", data, format="multipart")
        force_authenticate(request, self.admin)
        return view.as_view()(request, **kwargs)

    def existing_property(self):
        prop = Property.objects.create(**self.payload, background_image="old/cover")
        Amenity.objects.create(property=prop, category="extras", title="Old WiFi")
        PropertyImage.objects.create(property=prop, image="old/photo", category="bedroom")
        Highlight.objects.create(property=prop, title="Old highlight", image="old/highlight")
        return prop

    def assert_cleaned(self):
        self.cleanup.assert_has_calls([
            call(resource.public_id, resource_type="image", type="upload", invalidate=True)
            for resource in self.resources
        ])
        self.assertEqual(self.cleanup.call_count, len(self.resources))

    def test_common_formats_pass_image_validation(self):
        for image_format, extension in [("JPEG", "jpg"), ("JPEG", "jpeg"), ("PNG", "png"),
                                        ("WEBP", "webp"), ("GIF", "gif"), ("BMP", "bmp"),
                                        ("TIFF", "tif"), ("TIFF", "tiff")]:
            with self.subTest(image_format=image_format, extension=extension):
                validated = SupportedImageField().run_validation(image_file("photo." + extension, image_format))
                self.assertEqual(validated.image.format, image_format)

    def test_renaming_an_unsupported_image_does_not_bypass_validation(self):
        with self.assertRaisesMessage(ValidationError, "Unsupported image format 'ICO'"):
            SupportedImageField().run_validation(image_file("photo.jpg", "ICO"))

    def test_corrupted_image_is_rejected(self):
        with self.assertRaisesMessage(DjangoValidationError, "invalid, corrupted, or unsupported"):
            SupportedImageField().run_validation(SimpleUploadedFile("photo.png", b"not an image"))

    def test_invalid_property_images_are_rejected_before_any_upload_or_write(self):
        for field in ["background_image", "images", "highlights_images"]:
            with self.subTest(field=field):
                value = avif_file() if field == "background_image" else [image_file(), avif_file()]
                response = self.request(PropertyListCreateView, "post", dict(self.payload, **{field: value}))
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
                self.assertIn("AVIF", str(response.data))
                self.assertIn("JPG, JPEG, PNG, WebP, GIF, BMP, or TIFF", str(response.data))
                self.assertEqual(Property.objects.count(), 0)
                self.upload.assert_not_called()

    def test_invalid_file_field_is_not_silently_ignored(self):
        response = self.request(PropertyListCreateView, "post", dict(self.payload, image=avif_file()))
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unexpected image upload field", str(response.data["image"]))
        self.assertFalse(Property.objects.exists())

    def test_repeated_single_image_fields_cannot_hide_an_invalid_file(self):
        response = self.request(
            PropertyListCreateView, "post", dict(self.payload, background_image=[avif_file(), image_file()]),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Only one image file", str(response.data["background_image"]))
        self.assertFalse(Property.objects.exists())
        response = self.request(GalleryListView, "post", {"image": [avif_file(), image_file()]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Only one image file", str(response.data["image"]))
        self.assertFalse(Gallery.objects.exists())
        self.upload.assert_not_called()

    def test_failed_second_upload_rolls_back_property_and_all_nested_rows(self):
        self.upload.side_effect = [self.upload_success(None), CloudinaryError("storage unavailable")]
        payload = dict(self.payload, images=[image_file("first.png"), image_file("second.png")])
        payload["amenities"] = json.dumps({"extras": [{"title": "WiFi", "icon": "wifi"}]})
        payload["features"] = json.dumps([{"feature_type": "outdoor", "name": "Beach"}])
        response = self.request(PropertyListCreateView, "post", payload)
        self.assertEqual(response.status_code, 502)
        self.assertIn("images", response.data)
        self.assertIn("Image upload failed", str(response.data))
        self.assertNotIn("Unsupported image format", str(response.data))
        self.assertEqual(Property.objects.count(), 0)
        self.assertEqual(Amenity.objects.count(), 0)
        self.assertEqual(PropertyImage.objects.count(), 0)
        self.assert_cleaned()

    def test_failed_highlight_upload_rolls_back_created_property(self):
        response_payload = dict(self.payload, highlights_images=[image_file()])
        response_payload["highlights"] = json.dumps([{"title": "View", "image": None}])
        self.upload.side_effect = CloudinaryError("storage unavailable")
        response = self.request(PropertyListCreateView, "post", response_payload)
        self.assertEqual(response.status_code, 502)
        self.assertIn("highlights_images", response.data)
        self.assertFalse(Property.objects.exists())
        self.assertFalse(Highlight.objects.exists())

    def test_valid_combined_request_creates_property_and_images(self):
        payload = dict(self.payload, background_image=image_file("cover.png"), images=[image_file()])
        payload["highlights_images"] = [image_file("highlight.png")]
        payload["highlights"] = json.dumps([{"title": "View", "image": None}])
        payload["property_images"] = json.dumps([{"category": "bedroom", "order": 1}])
        response = self.request(PropertyListCreateView, "post", payload)
        self.assertEqual(response.status_code, 201, response.data)
        prop = Property.objects.get()
        self.assertTrue(prop.background_image)
        self.assertEqual(prop.images.count(), 1)
        self.assertEqual(prop.highlights.count(), 1)
        self.assertEqual(self.upload.call_count, 3)
        self.cleanup.assert_not_called()

    def test_invalid_update_preserves_existing_property_and_images(self):
        prop = self.existing_property()
        response = self.request(
            PropertyDetailView, "patch",
            {"description": "Changed", "images": [avif_file()]}, slug=prop.slug,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("images", response.data)
        self.assertNotIn("TRACEBACK", response.data)
        prop.refresh_from_db()
        self.assertEqual(prop.description, "Original description")
        self.assertEqual(prop.images.get().image.public_id, "old/photo")
        self.upload.assert_not_called()

    def test_upload_failure_during_update_restores_fields_and_deleted_related_rows(self):
        prop = self.existing_property()
        old_ids = {"image": prop.images.get().pk, "amenity": prop.amenities.get().pk,
                   "highlight": prop.highlights.get().pk}
        self.upload.side_effect = [self.upload_success(None), CloudinaryError("storage unavailable")]
        payload = {
            "name": "Renamed retreat", "description": "Changed",
            "background_image": image_file("cover.png"), "images": [image_file()],
            "amenities": json.dumps({"extras": [{"title": "New WiFi", "icon": "wifi"}]}),
            "highlights": json.dumps([]),
        }
        response = self.request(PropertyDetailView, "patch", payload, slug=prop.slug)
        self.assertEqual(response.status_code, 502, response.data)
        prop.refresh_from_db()
        self.assertEqual(prop.name, "Sample Retreat")
        self.assertEqual(prop.slug, "sample-retreat")
        self.assertEqual(prop.description, "Original description")
        self.assertEqual(prop.background_image.public_id, "old/cover")
        self.assertEqual(prop.images.get().pk, old_ids["image"])
        self.assertEqual(prop.amenities.get().pk, old_ids["amenity"])
        self.assertEqual(prop.highlights.get().pk, old_ids["highlight"])
        self.assert_cleaned()

    def test_database_failure_after_upload_cleans_up_new_file(self):
        from properties.serializers import PropertySerializer
        serializer = PropertySerializer(data=dict(self.payload, background_image=image_file(), images=[image_file()]))
        self.assertTrue(serializer.is_valid(), serializer.errors)
        with patch("properties.serializers.PropertyImage.objects.create", side_effect=IntegrityError("simulated DB error")):
            with self.assertRaises(IntegrityError):
                serializer.save()
        self.assertFalse(Property.objects.exists())
        self.assert_cleaned()

    def test_existing_highlight_url_does_not_consume_or_upload_an_existing_image(self):
        prop = self.existing_property()
        payload = {
            "highlights": json.dumps([
                {"title": "Existing", "image": "https://res.cloudinary.com/upload-tests/image/upload/old/highlight"},
                {"title": "New", "image": None},
            ]),
            "highlights_images": [image_file()],
        }
        response = self.request(PropertyDetailView, "patch", payload, slug=prop.slug)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(prop.highlights.count(), 2)
        self.assertEqual(self.upload.call_count, 1)
        self.cleanup.assert_not_called()

    def test_gallery_rejects_avif_and_preserves_existing_metadata(self):
        response = self.request(GalleryListView, "post", {"title": "New", "image": avif_file()})
        self.assertEqual(response.status_code, 400)
        self.assertIn("AVIF", str(response.data["image"]))
        self.assertFalse(Gallery.objects.exists())
        gallery = Gallery.objects.create(title="Original", image="old/gallery")
        response = self.request(GalleryDetailView, "patch", {"title": "Changed", "image": avif_file()}, pk=gallery.pk)
        self.assertEqual(response.status_code, 400)
        gallery.refresh_from_db()
        self.assertEqual(gallery.title, "Original")
        self.assertEqual(gallery.image.public_id, "old/gallery")
        self.upload.assert_not_called()

    def test_gallery_upload_failure_returns_service_error_without_saving(self):
        self.upload.side_effect = CloudinaryError("storage unavailable")
        response = self.request(GalleryListView, "post", {"title": "New", "image": image_file()})
        self.assertEqual(response.status_code, 502)
        self.assertIn("Image upload failed", str(response.data["image"]))
        self.assertFalse(Gallery.objects.exists())
        gallery = Gallery.objects.create(title="Original", image="old/gallery")
        response = self.request(
            GalleryDetailView, "patch", {"title": "Changed", "image": image_file()}, pk=gallery.pk,
        )
        self.assertEqual(response.status_code, 502)
        gallery.refresh_from_db()
        self.assertEqual(gallery.title, "Original")
        self.assertEqual(gallery.image.public_id, "old/gallery")

    def test_successful_gallery_upload_preserves_folder_and_response(self):
        response = self.request(GalleryListView, "post", {"title": "New", "image": image_file()})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Gallery.objects.get().title, "New")
        self.assertEqual(self.upload.call_args.kwargs, {"resource_type": "image", "folder": "gallery"})
        self.assertIn("https://res.cloudinary.com/", response.data["image"])
        self.cleanup.assert_not_called()
