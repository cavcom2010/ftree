from django.test import TestCase, override_settings


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
