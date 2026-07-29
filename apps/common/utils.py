import sys
from io import BytesIO

import blurhash
from PIL import Image
from django.core.files.uploadedfile import InMemoryUploadedFile


def compress_image(uploaded_image, quality=70, max_size=(1920, 1080)):
    """
    Compresses an image, converts to JPEG, and resizes if too large.
    Perfect for the 'Main' image view.
    """
    img = Image.open(uploaded_image)

    # Convert to RGB (fixes issues with PNG transparency)
    if img.mode != 'RGB':
        img = img.convert('RGB')

    # Resize if dimensions exceed max_size (maintain aspect ratio)
    img.thumbnail(max_size, Image.Resampling.LANCZOS)

    # Save to buffer
    output_io = BytesIO()
    img.save(output_io, format='JPEG', quality=quality, optimize=True)
    output_io.seek(0)

    # Return a new Django-friendly file object
    return InMemoryUploadedFile(
        output_io,
        'ImageField',
        f"{uploaded_image.name.split('.')[0]}.jpg",
        'image/jpeg',
        sys.getsizeof(output_io),
        None
    )


def generate_thumbnail(uploaded_image, size=(300, 300)):
    """
    Generates a small, highly compressed thumbnail.
    Perfect for 'List' views.
    """
    img = Image.open(uploaded_image)

    if img.mode != 'RGB':
        img = img.convert('RGB')

    # Smart Resize
    img.thumbnail(size, Image.Resampling.LANCZOS)

    output_io = BytesIO()
    img.save(output_io, format='JPEG', quality=60, optimize=True)  # Lower quality for thumbs
    output_io.seek(0)

    return InMemoryUploadedFile(
        output_io,
        'ImageField',
        f"thumb_{uploaded_image.name.split('.')[0]}.jpg",
        'image/jpeg',
        sys.getsizeof(output_io),
        None
    )


def generate_blurhash(uploaded_image, x_components=4, y_components=3):
    """
    Generates a blurhash string for the image.
    This allows the frontend to show a blurry placeholder while the image loads.
    """
    img = Image.open(uploaded_image)

    if img.mode != 'RGB':
        img = img.convert('RGB')

    # Resize to a very small size for hash generation to be fast
    img.thumbnail((100, 100))

    return blurhash.encode(img, x_components=x_components, y_components=y_components)