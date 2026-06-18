from django.core.management.base import BaseCommand
from django.db import transaction

from apps.families.models import Family, FamilyInvitation, FamilyMembership
from apps.memories.models import Memory
from apps.people.models import Person
from apps.relationships.models import Relationship
from apps.social.models import Activity
from apps.stories.models import Story


class Command(BaseCommand):
    help = (
        "Merge a source Person into a target Person. "
        "Reassigns all relationships, memberships, memories, stories, "
        "activities, and invitations from source to target, then deletes the source. "
        "Use --dry-run to preview changes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "source_id",
            type=int,
            help="ID of the Person to merge (will be deleted).",
        )
        parser.add_argument(
            "target_id",
            type=int,
            help="ID of the Person to merge into (will be kept).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without writing to the database.",
        )

    ROLED_PRIORITY = {
        FamilyMembership.Role.OWNER: 0,
        FamilyMembership.Role.ADMIN: 1,
        FamilyMembership.Role.MEMBER: 2,
        FamilyMembership.Role.VIEWER: 3,
    }

    def handle(self, *args, **options):
        source_id = options["source_id"]
        target_id = options["target_id"]
        dry_run = options["dry_run"]

        try:
            source = Person.objects.select_related("family").get(id=source_id)
        except Person.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Source person {source_id} not found."))
            return

        try:
            target = Person.objects.select_related("family").get(id=target_id)
        except Person.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Target person {target_id} not found."))
            return

        if source.family_id != target.family_id:
            self.stderr.write(self.style.ERROR(
                f"Source (family={source.family_id}) and target (family={target.family_id}) "
                "are not in the same family."
            ))
            return

        if source_id == target_id:
            self.stderr.write(self.style.ERROR("Source and target are the same person."))
            return

        self._print_plan(source, target)

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run complete. No changes made."))
            return

        self._execute_merge(source, target)
        self.stdout.write(self.style.SUCCESS(
            f"Merged {source} (id={source_id}) into {target} (id={target_id})."
        ))

    def _print_plan(self, source, target):
        self.stdout.write(f"Merging  source:  {source} (id={source.id})")
        self.stdout.write(f"   into target:  {target} (id={target.id})")
        self.stdout.write(f"   Family: {source.family.name} ({source.family.slug})")
        self.stdout.write("")

        actions = self._build_plan(source, target)
        if not actions:
            self.stdout.write("Nothing to merge.")
            return

        self.stdout.write("Plan:")
        for action in actions:
            self.stdout.write(f"  {action}")
        self.stdout.write(f"\n  DELETE {source} (id={source.id})")

    def _build_plan(self, source, target):
        actions = []

        # Relationships where source is from_person
        for rel in Relationship.objects.filter(from_person=source):
            dup = Relationship.objects.filter(
                family=rel.family,
                from_person=target,
                to_person=rel.to_person,
                relationship_type=rel.relationship_type,
            ).exists()
            if dup:
                actions.append(f"[SKIP] Relationship: {target} -> {rel.to_person} ({rel.relationship_type}) — already exists")
            else:
                actions.append(f"[MOVE] Relationship: {source} -> {rel.to_person} ({rel.relationship_type}) -> {target}")

        # Relationships where source is to_person
        for rel in Relationship.objects.filter(to_person=source):
            dup = Relationship.objects.filter(
                family=rel.family,
                from_person=rel.from_person,
                to_person=target,
                relationship_type=rel.relationship_type,
            ).exists()
            if dup:
                actions.append(f"[SKIP] Relationship: {rel.from_person} -> {target} ({rel.relationship_type}) — already exists")
            else:
                actions.append(f"[MOVE] Relationship: {rel.from_person} -> {source} ({rel.relationship_type}) -> {target}")

        # Activities
        activity_count = Activity.objects.filter(person=source).count()
        if activity_count:
            actions.append(f"[MOVE] {activity_count} activity record(s)")

        # Memberships
        source_membership = FamilyMembership.objects.filter(person=source).first()
        target_membership = FamilyMembership.objects.filter(person=target).first()
        if source_membership:
            if target_membership:
                source_role = self.ROLED_PRIORITY.get(source_membership.role, 99)
                target_role = self.ROLED_PRIORITY.get(target_membership.role, 99)
                if source_role < target_role:
                    actions.append(f"[UPGRADE] Membership role: target {target_role_label(target_membership.role)} -> {target_role_label(source_membership.role)}")
                else:
                    actions.append(f"[KEEP] Membership: target keeps {target_role_label(target_membership.role)} role (source had {target_role_label(source_membership.role)})")
            else:
                actions.append(f"[MOVE] Membership: {source_membership.user} -> {target} (role={target_role_label(source_membership.role)})")

        # Invitations
        inv_count = FamilyInvitation.objects.filter(person=source).count()
        if inv_count:
            actions.append(f"[MOVE] {inv_count} invitation(s) (person FK)")

        anchor_count = FamilyInvitation.objects.filter(anchor_person=source).count()
        if anchor_count:
            actions.append(f"[MOVE] {anchor_count} invitation(s) (anchor_person FK)")

        # Memories (M2M)
        memory_count = Memory.objects.filter(people=source).count()
        if memory_count:
            actions.append(f"[MERGE] {memory_count} memory(s) — add {target} to their people M2M")

        # Stories (M2M)
        story_count = Story.objects.filter(people=source).count()
        if story_count:
            actions.append(f"[MERGE] {story_count} story(ies) — add {target} to their people M2M")

        return actions

    @transaction.atomic
    def _execute_merge(self, source, target):
        # Relationships — from_person direction
        for rel in Relationship.objects.filter(from_person=source):
            if not Relationship.objects.filter(
                family=rel.family,
                from_person=target,
                to_person=rel.to_person,
                relationship_type=rel.relationship_type,
            ).exists():
                rel.from_person = target
                rel.save()
            else:
                rel.delete()

        # Relationships — to_person direction
        for rel in Relationship.objects.filter(to_person=source):
            if not Relationship.objects.filter(
                family=rel.family,
                from_person=rel.from_person,
                to_person=target,
                relationship_type=rel.relationship_type,
            ).exists():
                rel.to_person = target
                rel.save()
            else:
                rel.delete()

        # Activities
        Activity.objects.filter(person=source).update(person=target)

        # Memberships
        source_membership = FamilyMembership.objects.filter(person=source).first()
        target_membership = FamilyMembership.objects.filter(person=target).first()
        if source_membership:
            if target_membership:
                source_role = self.ROLED_PRIORITY.get(source_membership.role, 99)
                target_role = self.ROLED_PRIORITY.get(target_membership.role, 99)
                if source_role < target_role:
                    target_membership.role = source_membership.role
                    target_membership.save()
                source_membership.delete()
            else:
                source_membership.person = target
                source_membership.save()

        # Invitations
        FamilyInvitation.objects.filter(person=source).update(person=target)
        FamilyInvitation.objects.filter(anchor_person=source).update(anchor_person=target)

        # Memories M2M
        for memory in Memory.objects.filter(people=source):
            memory.people.add(target)

        # Stories M2M
        for story in Story.objects.filter(people=source):
            story.people.add(target)

        # Finally, delete the source
        source.delete()


def target_role_label(role):
    labels = {
        FamilyMembership.Role.OWNER: "OWNER",
        FamilyMembership.Role.ADMIN: "ADMIN",
        FamilyMembership.Role.MEMBER: "MEMBER",
        FamilyMembership.Role.VIEWER: "VIEWER",
    }
    return labels.get(role, str(role))
