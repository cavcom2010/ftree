from django.db.models.signals import pre_save
from django.dispatch import receiver

from apps.people.image_processing import normalise_profile_photo_upload
from apps.people.models import Person


@receiver(pre_save, sender=Person)
def normalise_person_profile_photo(sender, instance, raw=False, update_fields=None, **kwargs):
    """Resize/crop newly uploaded profile photos before Django stores them."""
    if raw or not instance.profile_photo:
        return

    if update_fields is not None and "profile_photo" not in update_fields:
        return

    # Only process fresh uploads. Already-stored files have _committed=True.
    if getattr(instance.profile_photo, "_committed", True):
        return

    processed_photo = normalise_profile_photo_upload(instance.profile_photo)
    if processed_photo is not None:
        instance.profile_photo = processed_photo
