from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image as PILImage

from apps.families.models import Family
from apps.people.models import Person


class PersonProfilePhotoTests(TestCase):
    def setUp(self):
        self.media_root = TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media_root.name)
        self.override.enable()
        self.family = Family.objects.create(name="Test Family", slug="test-family")

    def tearDown(self):
        self.override.disable()
        self.media_root.cleanup()

    def _uploaded_image(self, *, size=(2400, 1400), image_format="PNG"):
        image = PILImage.new("RGB", size, color=(120, 80, 40))
        buffer = BytesIO()
        image.save(buffer, format=image_format)
        return SimpleUploadedFile(
            "large-profile.png",
            buffer.getvalue(),
            content_type="image/png",
        )

    def test_profile_photo_upload_is_cropped_to_square_jpeg(self):
        person = Person.objects.create(
            family=self.family,
            first_name="Ada",
            last_name="Lovelace",
            profile_photo=self._uploaded_image(),
        )

        person.profile_photo.open("rb")
        try:
            with PILImage.open(person.profile_photo.file) as stored_image:
                self.assertEqual(stored_image.size, (512, 512))
                self.assertEqual(stored_image.format, "JPEG")
        finally:
            person.profile_photo.close()
