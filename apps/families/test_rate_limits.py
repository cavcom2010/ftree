from django.core.cache import cache
from django.test import TestCase

from apps.families.auth_views import _rate_limited


class RateLimitHelperTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_rate_limiter_blocks_after_configured_limit(self):
        self.assertFalse(_rate_limited("unit", "example", 2, 60))
        self.assertFalse(_rate_limited("unit", "example", 2, 60))
        self.assertTrue(_rate_limited("unit", "example", 2, 60))

    def test_rate_limiter_scopes_identifiers_separately(self):
        self.assertFalse(_rate_limited("unit", "one", 1, 60))
        self.assertFalse(_rate_limited("unit", "two", 1, 60))
        self.assertTrue(_rate_limited("unit", "one", 1, 60))
