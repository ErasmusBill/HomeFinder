import logging
from celery import shared_task
from django.core.files.base import ContentFile
from .models import PropertyMedia, Property
from apps.common.utils import compress_image, generate_blurhash, generate_thumbnail
from django.core.files import File
import os
import subprocess

logger = logging.getLogger(__name__)


@shared_task(name="process_property_cover", bind=True)
def process_property_cover(self, property_id):
    print(f"Processing cover image for property {property_id} in {self.request.hostname}")

    try:
        property_obj = Property.objects.get(pk=property_id)
    except Property.DoesNotExist:
        return

    if property_obj.cover_image:
        try:
            original_file = property_obj.cover_image

            compressed_file = compress_image(original_file)
            filename = original_file.name.split("/")[-1]

            property_obj.cover_image.save(filename, compressed_file, save=True)

            logger.info(f"Successfully compressed cover image for property {property_id}")

        except Exception as e:
            logger.error(f"Failed to process cover image for property {property_id}: {e}")


@shared_task(name="process_property_media", bind=True)
def process_property_media(self, media_id):
    print(f"Processing media {media_id} in {self.request.hostname}")

    try:
        media = PropertyMedia.objects.get(pk=media_id)
    except PropertyMedia.DoesNotExist:
        return

    if media.media_type == PropertyMedia.MediaType.IMAGE:
        try:
            original_file = media.file

            compressed_file = compress_image(original_file)
            filename = original_file.name.split("/")[-1]

            original_file.seek(0)
            thumbnail_file = generate_thumbnail(original_file)
            thumb_filename = f"thumb_{filename}"

            thumbnail_file.seek(0)
            media.blurhash = generate_blurhash(thumbnail_file)
            thumbnail_file.seek(0)

            media.file.save(filename, compressed_file, save=False)
            media.thumbnail.save(thumb_filename, thumbnail_file, save=False)

            # 5. Mark as processed
            media.is_processed = True
            media.save()

            logger.info(f"Successfully processed media {media_id}")

        except Exception as e:
            logger.error(f"Failed to process media {media_id}: {e}")

    elif media.media_type == PropertyMedia.MediaType.VIDEO:
        try:
            # We need the absolute path for FFmpeg
            input_path = media.file.path
            base_name = os.path.splitext(input_path)[0]
            thumb_path = f"{base_name}_thumb.jpg"
            # 1. Generate Thumbnail (Grab frame at 1 second)
            # cmd: ffmpeg -i input.mp4 -ss 00:00:01 -vframes 1 output.jpg
            subprocess.run([
                'ffmpeg', '-y', '-i', input_path,
                '-ss', '00:00:01', '-vframes', '1',
                thumb_path
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Save Thumbnail to model

            if os.path.exists(thumb_path):
                with open(thumb_path, 'rb') as f:
                    # Save the thumbnail file
                    django_file = File(f)
                    media.thumbnail.save(os.path.basename(thumb_path), django_file, save=False)

                    # NEW: Generate Blurhash from the video thumbnail
                    django_file.seek(0)
                    media.blurhash = generate_blurhash(django_file)

                os.remove(thumb_path)

                # 2. (Optional) Transcode to MP4 if needed

            # For MVP, we might skip full transcoding if it's expensive,

            # but getting the thumbnail is critical.

            media.is_processed = True

            media.save()

            logger.info(f"Video processed for {media_id}")


        except Exception as e:

            logger.error(f"Video processing failed for {media_id}: {e}")