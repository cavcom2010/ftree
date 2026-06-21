import io
import json
import tarfile
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.families.models import Family, FamilyBranch, FamilyMembership
from apps.people.models import Person
from apps.relationships.models import Relationship
from apps.social.models import Activity

User = get_user_model()


class ImportTreeStructureCommandTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="calvinmazhindu",
            email="calvin@example.com",
            password="secret",
        )

    def test_dry_run_does_not_mutate_database(self):
        old_family = self._existing_tree()
        fixture_path = self._write_fixture(self._valid_fixture())

        output = io.StringIO()
        call_command(
            "import_tree_structure",
            str(fixture_path),
            owner_username=self.owner.username,
            dry_run=True,
            stdout=output,
        )

        self.assertIn("Dry run complete", output.getvalue())
        self.assertTrue(Family.objects.filter(pk=old_family.pk).exists())
        self.assertFalse(Family.objects.filter(pk=101).exists())
        self.assertEqual(User.objects.count(), 1)

    def test_requires_confirmation_for_real_import(self):
        old_family = self._existing_tree()
        fixture_path = self._write_fixture(self._valid_fixture())

        with self.assertRaisesMessage(CommandError, "--confirm-clear-production-tree"):
            call_command(
                "import_tree_structure",
                str(fixture_path),
                owner_username=self.owner.username,
            )

        self.assertTrue(Family.objects.filter(pk=old_family.pk).exists())

    def test_import_replaces_tree_preserves_user_and_remaps_owner(self):
        old_family = self._existing_tree()
        fixture_path = self._write_fixture(self._valid_fixture())

        call_command(
            "import_tree_structure",
            str(fixture_path),
            owner_username=self.owner.username,
            confirm_clear_production_tree=True,
        )

        self.assertFalse(Family.objects.filter(pk=old_family.pk).exists())
        self.assertFalse(Activity.objects.filter(family=old_family).exists())
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(User.objects.filter(username="local-user").exists())

        family = Family.objects.get(pk=101)
        parent = Person.objects.get(pk=201)
        child = Person.objects.get(pk=202)
        branch = FamilyBranch.objects.get(pk=301)
        membership = FamilyMembership.objects.get(family=family, user=self.owner)

        self.assertEqual(family.created_by, self.owner)
        self.assertEqual(parent.created_by, self.owner)
        self.assertEqual(branch.created_by, self.owner)
        self.assertEqual(branch.root_person, parent)
        self.assertEqual(membership.role, FamilyMembership.Role.OWNER)
        self.assertEqual(membership.person, parent)
        self.assertTrue(
            Relationship.objects.filter(
                pk=401,
                family=family,
                from_person=parent,
                to_person=child,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).exists()
        )

        next_family = Family.objects.create(
            name="Next Family",
            slug="next-family",
            created_by=self.owner,
        )
        self.assertGreater(next_family.pk, family.pk)

    def test_invalid_relationship_is_rejected_before_clearing_existing_tree(self):
        old_family = self._existing_tree()
        fixture = self._valid_fixture()
        fixture.append(
            {
                "model": "families.family",
                "pk": 102,
                "fields": {
                    "name": "Other Imported Family",
                    "slug": "other-imported-family",
                    "description": "",
                    "created_by": ["local-user"],
                    "visibility": Family.Visibility.PRIVATE,
                    "public_summary": "",
                    "origin_summary": "",
                    "main_surnames": [],
                    "maiden_surnames": [],
                    "regions": [],
                    "allow_connection_requests": True,
                    "allow_public_surname_search": True,
                    "show_public_tree_shape": True,
                    "show_living_private_placeholders": True,
                    "created_at": self._now(),
                    "updated_at": self._now(),
                },
            }
        )
        fixture[3]["fields"]["family"] = 102
        fixture_path = self._write_fixture(fixture)

        with self.assertRaisesMessage(CommandError, "connects people outside its family"):
            call_command(
                "import_tree_structure",
                str(fixture_path),
                owner_username=self.owner.username,
                confirm_clear_production_tree=True,
            )

        self.assertTrue(Family.objects.filter(pk=old_family.pk).exists())

    def test_media_archive_is_extracted_under_profile_photos(self):
        fixture = self._valid_fixture()
        fixture[2]["fields"]["profile_photo"] = "people/profile-photos/photo.jpg"
        fixture_path = self._write_fixture(fixture)

        with tempfile.TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir) / "media"
            archive_path = Path(temp_dir) / "photos.tar.gz"
            self._write_tar_member(archive_path, "people/profile-photos/photo.jpg", b"image")

            with override_settings(MEDIA_ROOT=media_root):
                call_command(
                    "import_tree_structure",
                    str(fixture_path),
                    owner_username=self.owner.username,
                    confirm_clear_production_tree=True,
                    media_archive=str(archive_path),
                )

            self.assertEqual(
                (media_root / "people/profile-photos/photo.jpg").read_bytes(),
                b"image",
            )

    def test_unsafe_media_archive_is_rejected_before_clearing_existing_tree(self):
        old_family = self._existing_tree()
        fixture_path = self._write_fixture(self._valid_fixture())

        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "photos.tar.gz"
            self._write_tar_member(archive_path, "people/profile-photos/../../secret.txt", b"secret")

            with self.assertRaisesMessage(CommandError, "Unsafe media archive path"):
                call_command(
                    "import_tree_structure",
                    str(fixture_path),
                    owner_username=self.owner.username,
                    confirm_clear_production_tree=True,
                    media_archive=str(archive_path),
                )

        self.assertTrue(Family.objects.filter(pk=old_family.pk).exists())

    def test_sequence_reset_is_requested_after_explicit_primary_key_import(self):
        fixture_path = self._write_fixture(self._valid_fixture())

        with mock.patch(
            "apps.families.management.commands.import_tree_structure.Command._reset_sequences"
        ) as reset_sequences:
            call_command(
                "import_tree_structure",
                str(fixture_path),
                owner_username=self.owner.username,
                confirm_clear_production_tree=True,
            )

        reset_models = reset_sequences.call_args.args[0]
        self.assertIn(Family, reset_models)
        self.assertIn(Person, reset_models)
        self.assertIn(FamilyBranch, reset_models)
        self.assertIn(Relationship, reset_models)
        self.assertIn(FamilyMembership, reset_models)

    def _existing_tree(self):
        family = Family.objects.create(
            name="Production Family",
            slug="production-family",
            created_by=self.owner,
        )
        Activity.objects.create(
            family=family,
            actor=self.owner,
            activity_type=Activity.Type.PERSON_ADDED,
            message="Old activity",
        )
        Person.objects.create(
            family=family,
            first_name="Old",
            last_name="Person",
            created_by=self.owner,
        )
        return family

    def _valid_fixture(self):
        return [
            {
                "model": "families.family",
                "pk": 101,
                "fields": {
                    "name": "Imported Family",
                    "slug": "imported-family",
                    "description": "Imported description",
                    "created_by": ["local-user"],
                    "visibility": Family.Visibility.PRIVATE,
                    "public_summary": "",
                    "origin_summary": "Zimbabwe",
                    "main_surnames": ["Imported"],
                    "maiden_surnames": [],
                    "regions": ["Zimbabwe"],
                    "allow_connection_requests": True,
                    "allow_public_surname_search": True,
                    "show_public_tree_shape": True,
                    "show_living_private_placeholders": True,
                    "created_at": self._now(),
                    "updated_at": self._now(),
                },
            },
            {
                "model": "people.person",
                "pk": 201,
                "fields": {
                    "family": 101,
                    "first_name": "Parent",
                    "middle_name": "",
                    "last_name": "Imported",
                    "maiden_name": "",
                    "gender": Person.Gender.UNKNOWN,
                    "birth_date": None,
                    "death_date": None,
                    "birth_place": "",
                    "current_place": "",
                    "profile_photo": "",
                    "biography": "",
                    "is_living": True,
                    "is_private": False,
                    "visibility": Person.Visibility.PUBLIC_IF_DECEASED,
                    "public_notes": "",
                    "created_by": ["local-user"],
                    "created_at": self._now(),
                    "updated_at": self._now(),
                },
            },
            {
                "model": "people.person",
                "pk": 202,
                "fields": {
                    "family": 101,
                    "first_name": "Child",
                    "middle_name": "",
                    "last_name": "Imported",
                    "maiden_name": "",
                    "gender": Person.Gender.UNKNOWN,
                    "birth_date": None,
                    "death_date": None,
                    "birth_place": "",
                    "current_place": "",
                    "profile_photo": "",
                    "biography": "",
                    "is_living": True,
                    "is_private": False,
                    "visibility": Person.Visibility.PUBLIC_IF_DECEASED,
                    "public_notes": "",
                    "created_by": ["local-user"],
                    "created_at": self._now(),
                    "updated_at": self._now(),
                },
            },
            {
                "model": "relationships.relationship",
                "pk": 401,
                "fields": {
                    "family": 101,
                    "from_person": 201,
                    "to_person": 202,
                    "relationship_type": Relationship.Type.PARENT_CHILD,
                    "start_date": None,
                    "end_date": None,
                    "notes": "",
                    "created_at": self._now(),
                },
            },
            {
                "model": "families.familybranch",
                "pk": 301,
                "fields": {
                    "family": 101,
                    "name": "Main Branch",
                    "slug": "main",
                    "root_person": 201,
                    "description": "",
                    "is_public_showcase": False,
                    "allow_branch_requests": True,
                    "created_by": ["local-user"],
                    "created_at": self._now(),
                    "updated_at": self._now(),
                },
            },
            {
                "model": "families.familymembership",
                "pk": 501,
                "fields": {
                    "family": 101,
                    "user": ["local-user"],
                    "person": 201,
                    "role": FamilyMembership.Role.OWNER,
                    "joined_at": self._now(),
                },
            },
        ]

    def _write_fixture(self, fixture):
        temp_file = tempfile.NamedTemporaryFile(
            suffix=".json",
            mode="w",
            encoding="utf-8",
            delete=False,
        )
        with temp_file:
            json.dump(fixture, temp_file)
        path = Path(temp_file.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def _write_tar_member(self, archive_path, member_name, content):
        with tarfile.open(archive_path, "w:gz") as archive:
            info = tarfile.TarInfo(member_name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))

    def _now(self):
        return timezone.now().isoformat().replace("+00:00", "Z")
