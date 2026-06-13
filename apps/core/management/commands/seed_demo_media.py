import json
import mimetypes
import re
from io import StringIO
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from decouple import UndefinedValueError, config
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.families.models import Family
from apps.memories.models import Memory
from apps.people.models import Person
from apps.social.models import Activity
from apps.stories.models import Story


IMAGE_API_URL = "https://pixabay.com/api/"
VIDEO_API_URL = "https://pixabay.com/api/videos/"
MAX_DOWNLOAD_BYTES = 12 * 1024 * 1024

PROFILE_PHOTO_SEEDS = [
    {"person": "Robert", "query": "grandfather portrait smile"},
    {"person": "Margaret", "query": "grandmother portrait smile"},
    {"person": "James", "query": "father portrait family"},
    {"person": "Linda", "query": "mother portrait family"},
    {"person": "Michael", "query": "uncle portrait smile"},
    {"person": "Emily", "query": "woman portrait family"},
    {"person": "David", "query": "man portrait family"},
    {"person": "Laura", "query": "woman smile portrait"},
]

PHOTO_MEMORY_SEEDS = [
    {
        "title": "Summer Reunion on the Lawn",
        "query": "family reunion picnic",
        "people": ["James", "Linda", "Michael", "Emily", "David", "Laura"],
        "description": "A bright family gathering that anchors the Johnson cousins to the same branch.",
    },
    {
        "title": "Grandparents' Garden Afternoon",
        "query": "old garden family",
        "people": ["Robert", "Margaret"],
        "description": "A quiet afternoon in the garden, attached to the grandparents generation.",
    },
    {
        "title": "Kitchen Table Birthday",
        "query": "birthday family table",
        "people": ["David", "Olivia", "Noah"],
        "description": "A small birthday memory connected to David's children.",
    },
    {
        "title": "Wedding Portrait Keepsake",
        "query": "wedding family portrait",
        "people": ["Robert", "Margaret"],
        "description": "A formal keepsake for the couple at the top of the visible tree.",
    },
    {
        "title": "First House on Maple Street",
        "query": "family home house",
        "people": ["James", "Linda"],
        "description": "A place memory for the home where several family stories begin.",
    },
    {
        "title": "Cousins by the Lake",
        "query": "cousins lake family",
        "people": ["Emily", "David", "Laura"],
        "description": "A side-branch photo memory for the cousin generation.",
    },
    {
        "title": "Sunday Supper Table",
        "query": "family dinner table",
        "people": ["Margaret", "Linda", "David"],
        "description": "A warm supper memory tied to the recipes passed through the family.",
    },
    {
        "title": "Old Family Album Page",
        "query": "old photo album family",
        "people": ["Robert", "Margaret", "James"],
        "description": "An album-style memory that gives older generations more texture.",
    },
]

VIDEO_MEMORY_SEEDS = [
    {
        "title": "Picnic Blanket Video",
        "query": "family picnic",
        "people": ["Emily", "David", "Laura"],
        "description": "A short clip-style memory for the cousin branch.",
    },
    {
        "title": "Garden Walkthrough",
        "query": "garden family",
        "people": ["Robert", "Margaret"],
        "description": "A video memory for the grandparents' home and garden.",
    },
    {
        "title": "Birthday Candles Clip",
        "query": "birthday candles family",
        "people": ["Olivia", "Noah", "David"],
        "description": "A compact celebration video attached to the youngest generation.",
    },
]

STORY_ARTICLE_SEEDS = [
    {
        "title": "How Sunday Supper Became a Johnson Tradition",
        "people": ["Margaret", "Linda", "David"],
        "is_featured": True,
        "body": (
            "Every branch of the Johnson family remembers Sunday supper differently, "
            "but everyone remembers Margaret at the centre of the table. Her handwritten "
            "notes, small substitutions, and habit of saving the best seat for the newest "
            "guest turned an ordinary meal into a family ritual."
        ),
    },
    {
        "title": "Robert's Garden and the Lessons He Planted",
        "people": ["Robert", "James", "Michael"],
        "is_featured": True,
        "body": (
            "Robert's garden was less about perfect rows and more about patience. James "
            "learned how to repair tools there, Michael learned how to ask questions, and "
            "the grandchildren learned that stories often arrive while hands are busy."
        ),
    },
    {
        "title": "The Maple Street Years",
        "people": ["James", "Linda", "Emily"],
        "is_featured": False,
        "body": (
            "The Maple Street house gave the Johnsons a fixed point on the map. It held "
            "school photos, late-night phone calls, holiday coats by the door, and the "
            "first family albums that later became the start of the digital tree."
        ),
    },
    {
        "title": "A Cousins' Summer at the Lake",
        "people": ["Emily", "David", "Laura"],
        "is_featured": False,
        "body": (
            "The cousins still talk about the lake summer because it was the first time "
            "they understood themselves as their own generation. They carried stories from "
            "parents and grandparents, but made new ones around camp chairs and wet shoes."
        ),
    },
    {
        "title": "Why Olivia Keeps the Birthday Candle",
        "people": ["Olivia", "Noah", "David"],
        "is_featured": False,
        "body": (
            "Olivia saved one candle from a birthday cake and tucked it into a small box. "
            "For her, it marked the year she realised family memories are not only old "
            "photographs. They are small objects with a story attached."
        ),
    },
    {
        "title": "The Album Nobody Wanted to Throw Away",
        "people": ["Robert", "Margaret", "James", "Linda", "Michael"],
        "is_featured": False,
        "body": (
            "The oldest album had loose corners and fading ink, but nobody wanted to throw "
            "it away. It became a guide for rebuilding names, dates, and branches that had "
            "always been known by memory but never written down in one place."
        ),
    },
]


class Command(BaseCommand):
    help = "Seed richer demo photos, videos, and short articles using Pixabay media."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-downloads",
            action="store_true",
            help="Create database records without calling Pixabay or saving media files.",
        )
        parser.add_argument(
            "--limit-media",
            type=int,
            default=None,
            help="Maximum number of media files to download in this run.",
        )

    def handle(self, *args, **options):
        self.verbosity = options["verbosity"]
        self.skip_downloads = options["skip_downloads"]
        self.downloads_remaining = options["limit_media"]
        if self.downloads_remaining is not None and self.downloads_remaining < 0:
            raise CommandError("--limit-media must be zero or greater.")

        self.api_key = None if self.skip_downloads else self._get_api_key()

        family_stdout = self.stdout if self.verbosity > 0 else StringIO()
        call_command("seed_demo_family", verbosity=self.verbosity, stdout=family_stdout)

        with transaction.atomic():
            self.family = Family.objects.get(slug="johnson-family")
            self.user = User.objects.get(username="demo")
            self.people = {
                person.first_name: person
                for person in Person.objects.filter(family=self.family)
            }

            self._seed_profile_photos()
            memories = self._seed_memories()
            stories = self._seed_story_articles()
            self._seed_activities(memories, stories)

        self._write(self.style.SUCCESS("Demo media, videos, and short articles seeded successfully."))

    def _get_api_key(self):
        try:
            return config("PIXABAY_API_KEY")
        except UndefinedValueError as exc:
            raise CommandError("PIXABAY_API_KEY is required in .env.") from exc

    def _seed_profile_photos(self):
        for seed in PROFILE_PHOTO_SEEDS:
            person = self.people.get(seed["person"])
            if not person or person.profile_photo or not self._claim_download_slot():
                continue

            hit = self._first_image_hit(seed["query"], orientation="vertical")
            if not hit:
                continue

            image_url = hit.get("webformatURL") or hit.get("largeImageURL")
            if not image_url:
                continue

            person.profile_photo.save(
                self._filename_from_url(image_url, f"{person.first_name.lower()}-profile", ".jpg"),
                ContentFile(self._download_url(image_url)),
                save=True,
            )
            self._write(f"  Added profile photo for {person.full_name}")

    def _seed_memories(self):
        memories = []
        for seed in PHOTO_MEMORY_SEEDS:
            memories.append(self._seed_memory(seed, Memory.Type.PHOTO))
        for seed in VIDEO_MEMORY_SEEDS:
            memories.append(self._seed_memory(seed, Memory.Type.VIDEO))
        return [memory for memory in memories if memory]

    def _seed_memory(self, seed, memory_type):
        description = seed["description"]
        memory, created = Memory.objects.get_or_create(
            family=self.family,
            title=seed["title"],
            defaults={
                "description": description,
                "memory_type": memory_type,
                "uploaded_by": self.user,
            },
        )
        memory.memory_type = memory_type
        memory.uploaded_by = self.user
        if not memory.file:
            memory.description = description
        memory.save()
        memory.people.set(self._people_for(seed["people"]))

        if memory.file or not self._claim_download_slot():
            self._write(
                f"  Memory {memory.title} already has media"
                if memory.file
                else f"  Seeded memory record: {memory.title}"
            )
            return memory

        hit = (
            self._first_video_hit(seed["query"])
            if memory_type == Memory.Type.VIDEO
            else self._first_image_hit(seed["query"], orientation="horizontal")
        )
        if not hit:
            self._write(f"  Seeded memory record without media: {memory.title}")
            return memory

        source_user = hit.get("user", "Pixabay contributor")
        source_url = hit.get("pageURL", "https://pixabay.com/")
        memory.description = f"{description}\n\nMedia source: Pixabay / {source_user} ({source_url})"

        media_url, default_extension = self._media_url_for_hit(hit, memory_type)
        if media_url:
            memory.file.save(
                self._filename_from_url(media_url, self._slugish(memory.title), default_extension),
                ContentFile(self._download_url(media_url)),
                save=False,
            )
        memory.save()
        self._write(f"  Seeded {memory.get_memory_type_display().lower()} memory: {memory.title}")
        return memory

    def _seed_story_articles(self):
        stories = []
        for seed in STORY_ARTICLE_SEEDS:
            story, created = Story.objects.update_or_create(
                family=self.family,
                title=seed["title"],
                defaults={
                    "body": seed["body"],
                    "author": self.user,
                    "is_featured": seed["is_featured"],
                },
            )
            story.people.set(self._people_for(seed["people"]))
            stories.append(story)
            self._write(f"  Seeded short article: {story.title}")
        return stories

    def _seed_activities(self, memories, stories):
        for memory in memories:
            Activity.objects.get_or_create(
                family=self.family,
                actor=self.user,
                activity_type=Activity.Type.MEMORY_ADDED,
                message=f"Added memory: {memory.title}",
                memory=memory,
            )

        for story in stories:
            Activity.objects.get_or_create(
                family=self.family,
                actor=self.user,
                activity_type=Activity.Type.STORY_ADDED,
                message=f"Published short article: {story.title}",
                story=story,
            )

    def _people_for(self, names):
        return [self.people[name] for name in names if name in self.people]

    def _write(self, message):
        if self.verbosity > 0:
            self.stdout.write(message)

    def _claim_download_slot(self):
        if self.skip_downloads:
            return False
        if self.downloads_remaining is None:
            return True
        if self.downloads_remaining <= 0:
            return False
        self.downloads_remaining -= 1
        return True

    def _first_image_hit(self, query, orientation):
        payload = self._fetch_json(
            IMAGE_API_URL,
            {
                "key": self.api_key,
                "q": query,
                "image_type": "photo",
                "orientation": orientation,
                "category": "people",
                "safesearch": "true",
                "per_page": 6,
            },
        )
        return self._first_hit(payload)

    def _first_video_hit(self, query):
        payload = self._fetch_json(
            VIDEO_API_URL,
            {
                "key": self.api_key,
                "q": query,
                "video_type": "film",
                "category": "people",
                "safesearch": "true",
                "per_page": 6,
            },
        )
        return self._first_hit(payload)

    def _first_hit(self, payload):
        hits = payload.get("hits", [])
        return hits[0] if hits else None

    def _fetch_json(self, url, params):
        request = Request(
            f"{url}?{urlencode(params)}",
            headers={"User-Agent": "ftree-demo-seeder/1.0"},
        )
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise CommandError(f"Pixabay API request failed ({exc.code}): {detail}") from exc
        except (OSError, URLError, json.JSONDecodeError) as exc:
            raise CommandError(f"Pixabay API request failed: {exc}") from exc

    def _download_url(self, url):
        request = Request(url, headers={"User-Agent": "ftree-demo-seeder/1.0"})
        try:
            with urlopen(request, timeout=30) as response:
                content = response.read(MAX_DOWNLOAD_BYTES + 1)
        except (HTTPError, OSError, URLError) as exc:
            raise CommandError(f"Could not download Pixabay media: {exc}") from exc

        if len(content) > MAX_DOWNLOAD_BYTES:
            raise CommandError("Downloaded Pixabay media exceeded the 12MB limit.")
        return content

    def _media_url_for_hit(self, hit, memory_type):
        if memory_type == Memory.Type.VIDEO:
            videos = hit.get("videos", {})
            for size in ("tiny", "small", "medium"):
                video = videos.get(size) or {}
                if video.get("url"):
                    return video["url"], ".mp4"
            return "", ".mp4"

        return hit.get("webformatURL") or hit.get("largeImageURL") or "", ".jpg"

    def _filename_from_url(self, url, fallback_name, default_extension):
        path = PurePosixPath(urlparse(url).path)
        extension = path.suffix or default_extension
        if not extension and mimetypes.guess_type(url)[0]:
            extension = mimetypes.guess_extension(mimetypes.guess_type(url)[0])
        return f"pixabay/{fallback_name}{extension or default_extension}"

    def _slugish(self, value):
        return re.sub(r"-+", "-", "".join(char.lower() if char.isalnum() else "-" for char in value)).strip("-")
