from django.db import migrations, models
import django.db.models.deletion


def link_demo_membership_to_person(apps, schema_editor):
    FamilyMembership = apps.get_model("families", "FamilyMembership")
    Person = apps.get_model("people", "Person")

    demo_person = Person.objects.filter(
        family__slug="johnson-family",
        first_name="David",
        last_name="Johnson",
    ).first()
    if not demo_person:
        return

    FamilyMembership.objects.filter(
        family__slug="johnson-family",
        user__username="demo",
        person__isnull=True,
    ).update(person=demo_person)


def unlink_demo_membership_from_person(apps, schema_editor):
    FamilyMembership = apps.get_model("families", "FamilyMembership")
    FamilyMembership.objects.filter(
        family__slug="johnson-family",
        user__username="demo",
    ).update(person=None)


class Migration(migrations.Migration):

    dependencies = [
        ("people", "0001_initial"),
        ("families", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="familymembership",
            name="person",
            field=models.ForeignKey(
                blank=True,
                help_text="The family-tree person represented by this user.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="family_memberships",
                to="people.person",
            ),
        ),
        migrations.RunPython(
            link_demo_membership_to_person,
            reverse_code=unlink_demo_membership_from_person,
        ),
    ]
