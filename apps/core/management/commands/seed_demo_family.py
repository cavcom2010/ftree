from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from datetime import date

from apps.families.models import Family, FamilyMembership
from apps.people.models import Person
from apps.relationships.models import Relationship
from apps.stories.models import Story
from apps.social.models import Activity
from apps.achievements.models import Achievement, UserAchievement
from apps.prompts.models import FamilyPrompt


class Command(BaseCommand):
    help = "Seed a demo Johnson family with people, relationships, stories, and achievements."

    def handle(self, *args, **options):
        with transaction.atomic():
            self._seed_user()
            self._seed_family()
            self._seed_membership()
            self._seed_achievements()
            people = self._seed_people()
            self._seed_relationships(people)
            self._seed_stories(people)
            self._seed_activities(people)
            self._seed_user_achievements()
            self._seed_prompt()

        self.stdout.write(self.style.SUCCESS("Demo family seeded successfully."))

    @property
    def user(self):
        if not hasattr(self, "_user"):
            self._user = User.objects.get(username="demo")
        return self._user

    @property
    def family(self):
        if not hasattr(self, "_family"):
            self._family = Family.objects.get(slug="johnson-family")
        return self._family

    def _seed_user(self):
        user, created = User.objects.get_or_create(
            username="demo",
            defaults={
                "email": "demo@example.com",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            user.set_password("demo12345")
            user.save()
            self.stdout.write(f"  Created demo user")
        else:
            self.stdout.write(f"  Demo user already exists")

    def _seed_family(self):
        family, created = Family.objects.get_or_create(
            slug="johnson-family",
            defaults={
                "name": "Johnson Family",
                "description": "The Johnson family tree, spanning four generations.",
                "created_by": self.user,
            },
        )
        if created:
            self.stdout.write(f"  Created Johnson Family")
        else:
            self.stdout.write(f"  Johnson Family already exists")

    def _seed_membership(self):
        membership, created = FamilyMembership.objects.get_or_create(
            family=self.family,
            user=self.user,
            defaults={"role": FamilyMembership.Role.OWNER},
        )
        if created:
            self.stdout.write(f"  Added demo as owner of Johnson Family")
        else:
            self.stdout.write(f"  Demo membership already exists")

    def _seed_people(self):
        people_data = [
            {
                "first_name": "Robert",
                "last_name": "Johnson",
                "gender": Person.Gender.MALE,
                "birth_date": "1930-01-01",
                "death_date": "2005-01-01",
                "birth_place": "Chicago, IL",
                "is_living": False,
            },
            {
                "first_name": "Margaret",
                "last_name": "Johnson",
                "gender": Person.Gender.FEMALE,
                "birth_date": "1932-01-01",
                "death_date": "2010-01-01",
                "birth_place": "Detroit, MI",
                "is_living": False,
            },
            {
                "first_name": "James",
                "last_name": "Johnson",
                "gender": Person.Gender.MALE,
                "birth_date": "1955-01-01",
                "birth_place": "Chicago, IL",
            },
            {
                "first_name": "Linda",
                "last_name": "Johnson",
                "gender": Person.Gender.FEMALE,
                "birth_date": "1957-01-01",
                "birth_place": "Chicago, IL",
            },
            {
                "first_name": "Michael",
                "last_name": "Johnson",
                "gender": Person.Gender.MALE,
                "birth_date": "1960-01-01",
                "birth_place": "Chicago, IL",
            },
            {
                "first_name": "Emily",
                "last_name": "Johnson",
                "gender": Person.Gender.FEMALE,
                "birth_date": "1980-01-01",
                "birth_place": "Denver, CO",
            },
            {
                "first_name": "David",
                "last_name": "Johnson",
                "gender": Person.Gender.MALE,
                "birth_date": "1983-01-01",
                "birth_place": "Denver, CO",
            },
            {
                "first_name": "Laura",
                "last_name": "Johnson",
                "gender": Person.Gender.FEMALE,
                "birth_date": "1986-01-01",
                "birth_place": "Denver, CO",
            },
            {
                "first_name": "Olivia",
                "last_name": "Johnson",
                "gender": Person.Gender.FEMALE,
                "birth_date": "2008-01-01",
                "birth_place": "Seattle, WA",
            },
            {
                "first_name": "Noah",
                "last_name": "Johnson",
                "gender": Person.Gender.MALE,
                "birth_date": "2011-01-01",
                "birth_place": "Seattle, WA",
            },
        ]

        people = {}
        for data in people_data:
            first_name = data.pop("first_name")
            last_name = data.pop("last_name")
            person, created = Person.objects.get_or_create(
                family=self.family,
                first_name=first_name,
                last_name=last_name,
                defaults={**data, "created_by": self.user},
            )
            key = first_name
            people[key] = person
            if created:
                self.stdout.write(f"  Created {person.full_name}")
            else:
                self.stdout.write(f"  {person.full_name} already exists")

        return people

    def _seed_relationships(self, people):
        relationships = [
            ("Robert", "James", Relationship.Type.PARENT_CHILD),
            ("Margaret", "James", Relationship.Type.PARENT_CHILD),
            ("Robert", "Linda", Relationship.Type.PARENT_CHILD),
            ("Margaret", "Linda", Relationship.Type.PARENT_CHILD),
            ("Robert", "Michael", Relationship.Type.PARENT_CHILD),
            ("Margaret", "Michael", Relationship.Type.PARENT_CHILD),
            ("Linda", "Emily", Relationship.Type.PARENT_CHILD),
            ("Linda", "David", Relationship.Type.PARENT_CHILD),
            ("Linda", "Laura", Relationship.Type.PARENT_CHILD),
            ("David", "Olivia", Relationship.Type.PARENT_CHILD),
            ("David", "Noah", Relationship.Type.PARENT_CHILD),
        ]

        for from_name, to_name, rel_type in relationships:
            rel, created = Relationship.objects.get_or_create(
                family=self.family,
                from_person=people[from_name],
                to_person=people[to_name],
                relationship_type=rel_type,
            )
            if created:
                self.stdout.write(f"  Linked {from_name} → {to_name} ({rel_type.label})")
            else:
                self.stdout.write(f"  Relationship {from_name} → {to_name} already exists")

    def _seed_achievements(self):
        data = [
            {
                "code": "family_tree_starter",
                "name": "Family Tree Starter",
                "description": "Created your first family tree.",
                "icon": "tree",
            },
            {
                "code": "first_story",
                "name": "First Story",
                "description": "Published your first family story.",
                "icon": "book",
            },
            {
                "code": "family_historian",
                "name": "Family Historian",
                "description": "Added 10 people to your family tree.",
                "icon": "scroll",
            },
        ]
        for d in data:
            ach, created = Achievement.objects.get_or_create(
                code=d["code"],
                defaults=d,
            )
            if created:
                self.stdout.write(f"  Created achievement: {ach.name}")
            else:
                self.stdout.write(f"  Achievement {ach.name} already exists")

    def _seed_stories(self, people):
        stories_data = [
            {
                "title": "The Johnsons: A Family History",
                "body": (
                    "The Johnson family traces its roots back to the early 20th century "
                    "when Robert and Margaret Johnson settled in Chicago. Their three children "
                    "James, Linda, and Michael each went on to raise families of their own, "
                    "spreading the Johnson name across the Midwest and beyond."
                ),
                "people": ["Robert", "Margaret"],
                "is_featured": True,
            },
            {
                "title": "Grandpa Robert's War Stories",
                "body": (
                    "Robert Johnson served in the Korean War and came home with tales of "
                    "bravery and camaraderie. He often spoke of his time overseas as "
                    "the defining experience of his generation."
                ),
                "people": ["Robert"],
                "is_featured": False,
            },
            {
                "title": "Family Reunion 2020",
                "body": (
                    "Despite the challenges of 2020, the Johnson family found ways to "
                    "stay connected. Virtual game nights, shared recipes, and weekly calls "
                    "kept the family bond strong across four generations."
                ),
                "people": ["James", "Linda", "Michael", "Emily", "David", "Laura"],
                "is_featured": False,
            },
        ]

        for s in stories_data:
            person_names = s.pop("people")
            story, created = Story.objects.get_or_create(
                family=self.family,
                title=s["title"],
                defaults={**s, "author": self.user},
            )
            if created and person_names:
                story.people.add(*[people[n] for n in person_names])
                self.stdout.write(f"  Created story: {story.title}")
            elif created:
                self.stdout.write(f"  Created story: {story.title}")
            else:
                self.stdout.write(f"  Story {story.title} already exists")

    def _seed_activities(self, people):
        if Activity.objects.filter(family=self.family).exists():
            self.stdout.write(f"  Activities already exist, skipping")
            return

        activities = [
            (Activity.Type.PERSON_ADDED, "Added Robert Johnson to the family tree", people["Robert"], None, None),
            (Activity.Type.PERSON_ADDED, "Added Margaret Johnson to the family tree", people["Margaret"], None, None),
            (Activity.Type.PERSON_ADDED, "Added James Johnson to the family tree", people["James"], None, None),
            (Activity.Type.STORY_ADDED, "Published The Johnsons: A Family History", None, None, Story.objects.filter(family=self.family).first()),
        ]

        for act_type, message, person, memory, story in activities:
            Activity.objects.create(
                family=self.family,
                actor=self.user,
                activity_type=act_type,
                message=message,
                person=person,
                memory=memory,
                story=story,
            )
        self.stdout.write(f"  Created {len(activities)} activities")

    def _seed_user_achievements(self):
        achievements = Achievement.objects.all()
        count = 0
        for achievement in achievements:
            _, created = UserAchievement.objects.get_or_create(
                family=self.family,
                user=self.user,
                achievement=achievement,
            )
            if created:
                count += 1

        if count:
            self.stdout.write(f"  Awarded {count} achievements to demo user")
        else:
            self.stdout.write(f"  User achievements already exist")

    def _seed_prompt(self):
        today = date.today()
        prompt, created = FamilyPrompt.objects.get_or_create(
            family=self.family,
            active_date=today,
            defaults={
                "question": "What was your first job, and who helped you get it?",
            },
        )
        if created:
            self.stdout.write(f"  Created today's family prompt")
        else:
            self.stdout.write(f"  Today's prompt already exists")
