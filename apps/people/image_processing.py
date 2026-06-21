from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image as PILImage, ImageOps, UnidentifiedImageError


PROFILE_PHOTO_MAX_SIZE = 1024
PROFILE_PHOTO_QUALITY = 86


def _lanczos_filter():
    """Return the best available Pillow LANCZOS resampling filter."""
    if hasattr(PILImage, "Resampling"):
        return PILImage.Resampling.LANCZOS
    return PILImage.LANCZOS


def normalise_profile_photo_upload(profile_photo, *, max_size=PROFILE_PHOTO_MAX_SIZE):
    """
    Convert an uploaded profile photo into a web-friendly JPEG.

    The image is resized so its longest side is at most ``max_size`` pixels,
    preserving the original aspect ratio. The returned ContentFile is
    intentionally unsaved; assign it back to the ImageField before model
    storage runs so the original full-size upload is never persisted.
    """
    if not profile_photo:
        return None

    try:
        profile_photo.seek(0)
    except (AttributeError, OSError, ValueError):
        pass

    try:
        with PILImage.open(profile_photo) as source:
            image = ImageOps.exif_transpose(source)
            image = image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        return None

    image.thumbnail((max_size, max_size), resample=_lanczos_filter())

    output = BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=PROFILE_PHOTO_QUALITY,
        optimize=True,
        progressive=True,
    )

    stem = Path(getattr(profile_photo, "name", "") or "profile-photo").stem or "profile-photo"
    return ContentFile(output.getvalue(), name=f"{stem}.jpg")
