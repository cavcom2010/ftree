from tempfile import TemporaryDirectory
from unittest.mock import patch

from decouple import UndefinedValueError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.core.management.commands.seed_demo_media import (
    PHOTO_MEMORY_SEEDS,
    STORY_ARTICLE_SEEDS,
    VIDEO_MEMORY_SEEDS,
)
from apps.families.models import Family
from apps.memories.models import Memory
from apps.people.models import Person
from apps.stories.models import Story


@override_settings(ALLOWED_HOSTS=["testserver"])
class HomepageShellTests(TestCase):
    def test_homepage_returns_http_200(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

    def test_homepage_contains_tree_canvas(self):
        response = self.client.get("/")

        self.assertContains(response, 'id="tree-canvas"')

    def test_homepage_contains_generation_sections(self):
        response = self.client.get("/")

        self.assertContains(response, "generation-section")
        self.assertContains(response, "Gen -2")

    def test_homepage_contains_memory_rails_below_tree(self):
        response = self.client.get("/")
        content = response.content.decode()

        self.assertContains(response, "memory-rails")
        self.assertLess(content.index('id="tree-canvas"'), content.index("memory-rails"))


class SeedDemoMediaCommandTests(TestCase):
    def setUp(self):
        self.media_root = TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media_root.name)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        self.media_root.cleanup()

    def test_skip_downloads_creates_articles_and_memory_records_idempotently(self):
        call_command("seed_demo_media", "--skip-downloads", verbosity=0)
        call_command("seed_demo_media", "--skip-downloads", verbosity=0)

        family = Family.objects.get(slug="johnson-family")
        expected_memory_count = len(PHOTO_MEMORY_SEEDS) + len(VIDEO_MEMORY_SEEDS)

        self.assertEqual(Memory.objects.filter(family=family).count(), expected_memory_count)
        self.assertEqual(
            Story.objects.filter(family=family, title__in=[seed["title"] for seed in STORY_ARTICLE_SEEDS]).count(),
            len(STORY_ARTICLE_SEEDS),
        )
        self.assertTrue(
            Memory.objects.filter(family=family, title="Summer Reunion on the Lawn", people__first_name="David").exists()
        )

    def test_rerun_preserves_existing_pixabay_attribution(self):
        call_command("seed_demo_media", "--skip-downloads", verbosity=0)
        memory = Memory.objects.get(title="Summer Reunion on the Lawn")
        memory.file.name = "pixabay/summer-reunion.jpg"
        memory.description = f"{memory.description}\n\nMedia source: Pixabay / Demo (https://pixabay.com/)"
        memory.save()

        call_command("seed_demo_media", "--skip-downloads", verbosity=0)

        memory.refresh_from_db()
        self.assertIn("Media source: Pixabay / Demo", memory.description)

    @patch("apps.core.management.commands.seed_demo_media.config")
    def test_missing_pixabay_key_raises_clear_error(self, mock_config):
        mock_config.side_effect = UndefinedValueError("PIXABAY_API_KEY")

        with self.assertRaisesMessage(CommandError, "PIXABAY_API_KEY is required"):
            call_command("seed_demo_media", verbosity=0)

        self.assertFalse(Family.objects.exists())

    @patch("apps.core.management.commands.seed_demo_media.Command._download_url")
    @patch("apps.core.management.commands.seed_demo_media.Command._fetch_json")
    @patch("apps.core.management.commands.seed_demo_media.config")
    def test_limit_media_caps_downloaded_files(self, mock_config, mock_fetch_json, mock_download_url):
        mock_config.return_value = "fake-key"
        mock_download_url.return_value = b"fake-media-bytes"

        def fake_fetch(url, params):
            if "videos" in url:
                return {
                    "hits": [
                        {
                            "pageURL": "https://pixabay.com/videos/demo-1/",
                            "user": "Video Maker",
                            "videos": {"tiny": {"url": "https://cdn.pixabay.com/video/demo_tiny.mp4"}},
                        }
                    ]
                }
            return {
                "hits": [
                    {
                        "pageURL": "https://pixabay.com/photos/demo-1/",
                        "user": "Photo Maker",
                        "webformatURL": "https://cdn.pixabay.com/photo/demo_640.jpg",
                    }
                ]
            }

        mock_fetch_json.side_effect = fake_fetch

        call_command("seed_demo_media", "--limit-media", "2", verbosity=0)

        profile_file_count = Person.objects.exclude(profile_photo="").count()
        memory_file_count = Memory.objects.exclude(file="").count()

        self.assertEqual(profile_file_count + memory_file_count, 2)
