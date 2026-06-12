from django.test import TestCase, override_settings

from apps.families.models import Family


@override_settings(ALLOWED_HOSTS=["testserver"])
class MemoryListViewTests(TestCase):
    def test_memory_list_does_not_require_homepage_generation_context(self):
        Family.objects.create(name="Johnson Family", slug="johnson-family")

        response = self.client.get("/memories/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Memories")
