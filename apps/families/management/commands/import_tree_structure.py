import json
import shutil
import tarfile
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import DatabaseError, connection, transaction

from apps.families.models import Family, FamilyBranch, FamilyMembership
from apps.people.models import Person
from apps.relationships.models import Relationship


TREE_MODEL_ORDER = (Family, Person, FamilyBranch, Relationship)
TREE_MODELS = {model._meta.label_lower: model for model in TREE_MODEL_ORDER}
MEMBERSHIP_LABEL = FamilyMembership._meta.label_lower
SUPPORTED_LABELS = set(TREE_MODELS) | {MEMBERSHIP_LABEL}
OWNER_FIELD_NAMES = {"created_by"}
PROFILE_PHOTO_PREFIX = PurePosixPath("people/profile-photos")


class Command(BaseCommand):
    help = (
        "Replace the production tree structure from a safe fixture export. "
        "Production users are preserved and imported tree ownership is remapped "
        "to the selected owner."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "fixture_path",
            help="Path to the tree-structure JSON fixture created with dumpdata.",
        )
        parser.add_argument(
            "--owner-username",
            required=True,
            help="Existing active production username that will own the imported tree.",
        )
        parser.add_argument(
            "--confirm-clear-production-tree",
            action="store_true",
            help="Required for real imports because all existing Family rows are deleted first.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and summarize the import without changing the database or media files.",
        )
        parser.add_argument(
            "--media-archive",
            default="",
            help="Optional tar archive rooted at media/ containing people/profile-photos/ files.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if not dry_run and not options["confirm_clear_production_tree"]:
            raise CommandError(
                "Refusing to clear production tree data without --confirm-clear-production-tree."
            )

        owner = self._get_owner(options["owner_username"])
        fixture = self._load_fixture(options["fixture_path"])
        import_plan = self._build_import_plan(fixture, owner)
        media_members = self._validate_media_archive(options["media_archive"])

        self._write_summary(import_plan, owner, dry_run=dry_run, media_members=media_members)
        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run complete. No database rows or media files changed."))
            return

        self._replace_tree(import_plan)
        extracted_count = self._extract_media_archive(options["media_archive"]) if options["media_archive"] else 0

        if extracted_count:
            self.stdout.write(self.style.SUCCESS(f"Extracted {extracted_count} profile photo file(s)."))
        self.stdout.write(self.style.SUCCESS("Tree structure import complete."))

    def _get_owner(self, username):
        User = get_user_model()
        username_field = User.USERNAME_FIELD
        try:
            return User._default_manager.get(**{username_field: username}, is_active=True)
        except User.DoesNotExist as exc:
            raise CommandError(f"No active production user found for {username!r}.") from exc

    def _load_fixture(self, fixture_path):
        path = Path(fixture_path)
        if not path.is_file():
            raise CommandError(f"Fixture file does not exist: {path}")

        try:
            with path.open(encoding="utf-8") as fixture_file:
                data = json.load(fixture_file)
        except json.JSONDecodeError as exc:
            raise CommandError(f"Fixture is not valid JSON: {exc}") from exc
        except OSError as exc:
            raise CommandError(f"Could not read fixture: {exc}") from exc

        if not isinstance(data, list):
            raise CommandError("Fixture must be a JSON list of serialized Django objects.")

        grouped = {label: [] for label in SUPPORTED_LABELS}
        seen_pks = {label: set() for label in SUPPORTED_LABELS}
        for index, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                raise CommandError(f"Fixture item #{index} is not an object.")

            label = str(item.get("model", "")).lower()
            if label not in SUPPORTED_LABELS:
                supported = ", ".join(sorted(SUPPORTED_LABELS))
                raise CommandError(
                    f"Unsupported fixture model {label!r}. Export only these models: {supported}."
                )

            if "pk" not in item or "fields" not in item or not isinstance(item["fields"], dict):
                raise CommandError(f"Fixture item #{index} must contain pk and fields.")

            pk = self._pk_value(item["pk"], field_name="pk", model_label=label)
            if pk in seen_pks[label]:
                raise CommandError(f"Duplicate primary key {pk} for {label}.")

            item = {**item, "model": label, "pk": pk}
            grouped[label].append(item)
            seen_pks[label].add(pk)

        return grouped

    def _build_import_plan(self, fixture, owner):
        family_ids = {item["pk"] for item in fixture[Family._meta.label_lower]}
        person_family_ids = self._person_family_map(fixture[Person._meta.label_lower], family_ids)
        self._validate_branches(fixture[FamilyBranch._meta.label_lower], family_ids, person_family_ids)
        self._validate_relationships(fixture[Relationship._meta.label_lower], family_ids, person_family_ids)
        membership_anchors = self._membership_anchors(
            fixture[MEMBERSHIP_LABEL],
            family_ids,
            person_family_ids,
        )

        instances = {
            model._meta.label_lower: [
                self._build_instance(model, item, owner)
                for item in fixture[model._meta.label_lower]
            ]
            for model in TREE_MODEL_ORDER
        }

        first_person_by_family = {}
        for person_id, family_id in sorted(person_family_ids.items()):
            first_person_by_family.setdefault(family_id, person_id)

        owner_memberships = [
            FamilyMembership(
                family_id=family_id,
                user=owner,
                person_id=membership_anchors.get(family_id) or first_person_by_family.get(family_id),
                role=FamilyMembership.Role.OWNER,
            )
            for family_id in sorted(family_ids)
        ]

        return {
            "instances": instances,
            "owner_memberships": owner_memberships,
        }

    def _person_family_map(self, people, family_ids):
        person_family_ids = {}
        for item in people:
            family_id = self._fixture_fk(item, "family")
            if family_id not in family_ids:
                raise CommandError(
                    f"Person {item['pk']} references missing family {family_id}."
                )
            person_family_ids[item["pk"]] = family_id
        return person_family_ids

    def _validate_branches(self, branches, family_ids, person_family_ids):
        for item in branches:
            family_id = self._fixture_fk(item, "family")
            if family_id not in family_ids:
                raise CommandError(
                    f"FamilyBranch {item['pk']} references missing family {family_id}."
                )

            root_person_id = self._fixture_fk(item, "root_person", required=False)
            if root_person_id is None:
                continue
            if root_person_id not in person_family_ids:
                raise CommandError(
                    f"FamilyBranch {item['pk']} references missing root person {root_person_id}."
                )
            if person_family_ids[root_person_id] != family_id:
                raise CommandError(
                    f"FamilyBranch {item['pk']} root person belongs to a different family."
                )

    def _validate_relationships(self, relationships, family_ids, person_family_ids):
        valid_types = {choice[0] for choice in Relationship.Type.choices}
        for item in relationships:
            fields = item["fields"]
            family_id = self._fixture_fk(item, "family")
            from_person_id = self._fixture_fk(item, "from_person")
            to_person_id = self._fixture_fk(item, "to_person")
            relationship_type = fields.get("relationship_type")

            if family_id not in family_ids:
                raise CommandError(
                    f"Relationship {item['pk']} references missing family {family_id}."
                )
            if from_person_id not in person_family_ids:
                raise CommandError(
                    f"Relationship {item['pk']} references missing from_person {from_person_id}."
                )
            if to_person_id not in person_family_ids:
                raise CommandError(
                    f"Relationship {item['pk']} references missing to_person {to_person_id}."
                )
            if from_person_id == to_person_id:
                raise CommandError(f"Relationship {item['pk']} points to the same person.")
            if person_family_ids[from_person_id] != family_id or person_family_ids[to_person_id] != family_id:
                raise CommandError(
                    f"Relationship {item['pk']} connects people outside its family."
                )
            if relationship_type not in valid_types:
                raise CommandError(
                    f"Relationship {item['pk']} has invalid type {relationship_type!r}."
                )

    def _membership_anchors(self, memberships, family_ids, person_family_ids):
        anchors = {}
        for item in memberships:
            family_id = self._fixture_fk(item, "family")
            if family_id not in family_ids:
                raise CommandError(
                    f"FamilyMembership {item['pk']} references missing family {family_id}."
                )

            person_id = self._fixture_fk(item, "person", required=False)
            if person_id is None:
                continue
            if person_id not in person_family_ids:
                raise CommandError(
                    f"FamilyMembership {item['pk']} references missing person {person_id}."
                )
            if person_family_ids[person_id] != family_id:
                raise CommandError(
                    f"FamilyMembership {item['pk']} person belongs to a different family."
                )
            anchors.setdefault(family_id, person_id)
        return anchors

    def _fixture_fk(self, item, field_name, required=True):
        fields = item["fields"]
        if field_name not in fields:
            if required:
                raise CommandError(f"{item['model']} {item['pk']} is missing {field_name}.")
            return None

        value = fields[field_name]
        if value is None:
            if required:
                raise CommandError(f"{item['model']} {item['pk']} has null {field_name}.")
            return None
        return self._pk_value(value, field_name=field_name, model_label=item["model"])

    def _build_instance(self, model, item, owner):
        fields = item["fields"]
        kwargs = {model._meta.pk.attname: item["pk"]}

        for field in model._meta.concrete_fields:
            if field.primary_key or field.name not in fields:
                continue
            if field.name in OWNER_FIELD_NAMES:
                kwargs[field.attname] = owner.pk
                continue

            value = fields[field.name]
            if field.remote_field:
                kwargs[field.attname] = (
                    None
                    if value is None
                    else self._pk_value(value, field_name=field.name, model_label=item["model"])
                )
            else:
                kwargs[field.name] = self._field_value(field, value, item)

        for owner_field in OWNER_FIELD_NAMES:
            try:
                field = model._meta.get_field(owner_field)
            except FieldDoesNotExist:
                continue
            kwargs[field.attname] = owner.pk

        return model(**kwargs)

    def _field_value(self, field, value, item):
        try:
            return field.to_python(value)
        except ValidationError as exc:
            raise CommandError(
                f"Invalid value for {item['model']} {item['pk']} field {field.name}: {exc}"
            ) from exc

    def _pk_value(self, value, field_name, model_label):
        if isinstance(value, (list, tuple, dict)):
            raise CommandError(
                f"{model_label}.{field_name} must use integer primary keys, not natural keys."
            )
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise CommandError(f"{model_label}.{field_name} must be an integer primary key.") from exc

    def _write_summary(self, import_plan, owner, dry_run, media_members):
        action = "Would clear" if dry_run else "Will clear"
        existing_family_count = Family.objects.count()
        instances = import_plan["instances"]
        memberships = import_plan["owner_memberships"]

        self.stdout.write(f"{action} {existing_family_count} existing production family tree(s).")
        self.stdout.write(
            "Fixture contains "
            f"{len(instances[Family._meta.label_lower])} family/families, "
            f"{len(instances[Person._meta.label_lower])} person/people, "
            f"{len(instances[FamilyBranch._meta.label_lower])} branch(es), "
            f"{len(instances[Relationship._meta.label_lower])} relationship(s)."
        )
        self.stdout.write(
            f"{'Would create' if dry_run else 'Will create'} {len(memberships)} owner membership(s) "
            f"for {owner.get_username()}."
        )
        if media_members:
            self.stdout.write(
                f"{'Would extract' if dry_run else 'Will extract'} "
                f"{sum(1 for member in media_members if member.isfile())} profile photo file(s)."
            )

    def _replace_tree(self, import_plan):
        try:
            with transaction.atomic():
                deleted_count, _ = Family.objects.all().delete()
                self.stdout.write(f"Cleared {deleted_count} existing tree-related row(s).")

                instances = import_plan["instances"]
                for model in TREE_MODEL_ORDER:
                    model.objects.bulk_create(instances[model._meta.label_lower])

                FamilyMembership.objects.bulk_create(import_plan["owner_memberships"])
                self._reset_sequences((*TREE_MODEL_ORDER, FamilyMembership))
        except DatabaseError as exc:
            raise CommandError(f"Import failed and was rolled back: {exc}") from exc

    def _reset_sequences(self, models):
        statements = connection.ops.sequence_reset_sql(no_style(), models)
        if not statements:
            return

        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

    def _validate_media_archive(self, archive_path):
        if not archive_path:
            return []

        path = Path(archive_path)
        if not path.is_file():
            raise CommandError(f"Media archive does not exist: {path}")

        try:
            with tarfile.open(path, "r:*") as archive:
                members = archive.getmembers()
        except (tarfile.TarError, OSError) as exc:
            raise CommandError(f"Could not read media archive: {exc}") from exc

        for member in members:
            self._safe_media_member_path(member)
        return members

    def _extract_media_archive(self, archive_path):
        if not archive_path:
            return 0

        media_root = Path(settings.MEDIA_ROOT).resolve()
        extracted_count = 0
        with tarfile.open(archive_path, "r:*") as archive:
            for member in archive.getmembers():
                relative_path = self._safe_media_member_path(member)
                target = media_root.joinpath(*relative_path.parts)
                resolved_target = target.resolve(strict=False)
                if not resolved_target.is_relative_to(media_root):
                    raise CommandError(f"Unsafe media archive path: {member.name}")

                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise CommandError(f"Could not extract media archive member: {member.name}")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                extracted_count += 1

        return extracted_count

    def _safe_media_member_path(self, member):
        if not (member.isfile() or member.isdir()):
            raise CommandError(f"Unsupported media archive member type: {member.name}")
        if member.issym() or member.islnk():
            raise CommandError(f"Media archive links are not allowed: {member.name}")

        name = member.name.replace("\\", "/")
        while name.startswith("./"):
            name = name[2:]
        path = PurePosixPath(name)

        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise CommandError(f"Unsafe media archive path: {member.name}")
        if path != PROFILE_PHOTO_PREFIX and not path.is_relative_to(PROFILE_PHOTO_PREFIX):
            raise CommandError(
                f"Media archive member must be under {PROFILE_PHOTO_PREFIX}/: {member.name}"
            )
        return path
