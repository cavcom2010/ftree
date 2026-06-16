from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.families.models import Family, FamilyMembership
from apps.people.models import Person
from apps.social.models import Activity
from apps.stories.models import Story


User = get_user_model()


class StoryCreatePersonTagTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="story-user",
            email="story@example.com",
            password="secret",
        )
        self.family = Family.objects.create(
            name="Story Family",
            slug="story-family",
            created_by=self.user,
        )
        self.person = Person.objects.create(
            family=self.family,
            first_name="Tagged",
            last_name="Person",
            created_by=self.user,
        )
        FamilyMembership.objects.create(
            family=self.family,
            user=self.user,
            person=self.person,
            role=FamilyMembership.Role.OWNER,
        )

    def test_story_create_prefills_selected_person(self):
        self.client.force_login(self.user)

        response = self.client.get(f"/stories/create/?person={self.person.id}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'name="person" value="{self.person.id}"')
        self.assertContains(response, "Tagged Person")

    def test_story_create_tags_selected_person(self):
        self.client.force_login(self.user)

        response = self.client.post(
            "/stories/create/",
            {
                "title": "A tagged story",
                "body": "This story belongs to the selected person.",
                "is_featured": "",
                "person": str(self.person.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        story = Story.objects.get(title="A tagged story")
        self.assertTrue(story.people.filter(id=self.person.id).exists())
        self.assertTrue(
            Activity.objects.filter(
                story=story,
                person=self.person,
                message="Published A tagged story",
            ).exists()
        )

    def test_story_create_ignores_person_from_other_family(self):
        other_family = Family.objects.create(name="Other Family", slug="other-family")
        other_person = Person.objects.create(
            family=other_family,
            first_name="Other",
            last_name="Person",
        )
        self.client.force_login(self.user)

        self.client.post(
            "/stories/create/",
            {
                "title": "Scoped story",
                "body": "This should not tag an outside person.",
                "is_featured": "",
                "person": str(other_person.id),
            },
        )

        story = Story.objects.get(title="Scoped story")
        self.assertFalse(story.people.exists())
