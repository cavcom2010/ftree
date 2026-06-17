from django.core.management.base import BaseCommand

from apps.families.models import Family
from apps.people.models import Person
from apps.relationships.models import Relationship


class Command(BaseCommand):
    help = (
        "Repair missing parent_child links for siblings. "
        "By default, when one sibling has parents and the other does not, the "
        "orphan sibling is linked to the known parents. Use --aggressive to also "
        "fill missing parents for pairs that already share at least one parent. "
        "Use --dry-run to preview changes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--family",
            dest="family_slug",
            help="Limit repair to a single family slug.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without writing to the database.",
        )
        parser.add_argument(
            "--aggressive",
            action="store_true",
            help=(
                "For any sibling pair that shares at least one parent, treat all "
                "parents on either side as shared and create the missing links. "
                "This assumes full siblings; use with care."
            ),
        )

    def handle(self, *args, **options):
        family_slug = options["family_slug"]
        dry_run = options["dry_run"]
        aggressive = options["aggressive"]

        families = Family.objects.all()
        if family_slug:
            families = families.filter(slug=family_slug)

        created_count = 0
        skipped_count = 0

        for family in families:
            self.stdout.write(f"Processing family: {family.name} ({family.slug})")
            family_created, family_skipped = self._repair_family(
                family, dry_run=dry_run, aggressive=aggressive
            )
            created_count += family_created
            skipped_count += family_skipped

        mode = "Would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(
            f"{mode} {created_count} parent-child relationship(s). Skipped {skipped_count} ambiguous pair(s)."
        ))

    def _repair_family(self, family, dry_run, aggressive):
        created = 0
        skipped = 0

        # Use a set of unordered sibling pairs to avoid duplicate work.
        sibling_pairs = set()
        for from_id, to_id in (
            Relationship.objects.filter(
                family=family,
                relationship_type=Relationship.Type.SIBLING,
            )
            .values_list("from_person_id", "to_person_id")
        ):
            sibling_pairs.add((min(from_id, to_id), max(from_id, to_id)))

        for a_id, b_id in sibling_pairs:
            parents_a = self._direct_parent_ids(family, a_id)
            parents_b = self._direct_parent_ids(family, b_id)

            missing_for_a = set()
            missing_for_b = set()

            if not parents_a and not parents_b:
                skipped += 1
                continue

            if not parents_a and not parents_b:
                skipped += 1
                continue

            if not parents_a:
                # A has no parents; infer all of B's parents for A.
                missing_for_a = set(parents_b)
            elif not parents_b:
                # B has no parents; infer all of A's parents for B.
                missing_for_b = set(parents_a)
            elif aggressive:
                shared = parents_a & parents_b
                if not shared:
                    skipped += 1
                    continue
                # Treat the union of known parents as shared.
                union = parents_a | parents_b
                missing_for_a = union - parents_a
                missing_for_b = union - parents_b
            else:
                # Both have parents but not in aggressive mode; leave as-is.
                skipped += 1
                continue

            created += self._create_missing_links(
                family, a_id, missing_for_a, dry_run
            )
            created += self._create_missing_links(
                family, b_id, missing_for_b, dry_run
            )

        return created, skipped

    def _direct_parent_ids(self, family, person_id):
        parent_types = [
            Relationship.Type.PARENT_CHILD,
            Relationship.Type.ADOPTIVE_PARENT,
            Relationship.Type.STEP_PARENT,
            Relationship.Type.GUARDIAN,
        ]
        return set(
            Relationship.objects.filter(
                family=family,
                to_person_id=person_id,
                relationship_type__in=parent_types,
            ).values_list("from_person_id", flat=True)
        )

    def _create_missing_links(self, family, child_id, parent_ids, dry_run):
        created = 0
        for parent_id in parent_ids:
            exists = Relationship.objects.filter(
                family=family,
                from_person_id=parent_id,
                to_person_id=child_id,
                relationship_type=Relationship.Type.PARENT_CHILD,
            ).exists()
            if exists:
                continue

            parent = Person.objects.get(id=parent_id)
            child = Person.objects.get(id=child_id)
            self.stdout.write(
                f"  {'Would create' if dry_run else 'Creating'}: "
                f"{parent.full_name} -> {child.full_name} (parent_child)"
            )
            if not dry_run:
                Relationship.objects.create(
                    family=family,
                    from_person=parent,
                    to_person=child,
                    relationship_type=Relationship.Type.PARENT_CHILD,
                )
            created += 1
        return created
