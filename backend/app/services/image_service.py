"""Normalizacion de imagenes antes de enviarlas a Claude.

Toda foto entrante se convierte a JPEG RGB con un lado largo maximo. Esto
resuelve tres cosas a la vez:

- HEIC/HEIF (formato por defecto del iPhone) no lo acepta la API de Anthropic.
- Fotos de movil de 12 MP pueden superar el limite de 5 MB por imagen.
- La resolucion por encima de IMAGE_MAX_DIMENSION no aporta precision al
  analisis y se paga igual en tokens de vision.
"""

import io
import os
import uuid

from PIL import Image, ImageOps

try:  # HEIC/HEIF necesita un plugin externo
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:  # pragma: no cover - depende del entorno
    HEIF_SUPPORTED = False


class UnsupportedImageError(ValueError):
    """La imagen no se puede decodificar o su formato no es compatible."""


def normalize_image(raw: bytes, max_dimension: int, quality: int) -> tuple[bytes, str]:
    """Devuelve (bytes_jpeg, media_type) listos para la API de Anthropic."""
    try:
        with Image.open(io.BytesIO(raw)) as img:
            # Aplica la rotacion EXIF: sin esto las fotos verticales de movil
            # llegan tumbadas y Claude estima peor las porciones.
            img = ImageOps.exif_transpose(img)

            # JPEG solo admite RGB: descarta alfa de PNG/WebP y paletas de GIF.
            if img.mode != 'RGB':
                img = img.convert('RGB')

            if max(img.size) > max_dimension:
                img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=quality, optimize=True)
            return buffer.getvalue(), 'image/jpeg'
    except UnsupportedImageError:
        raise
    except Exception as exc:  # Pillow lanza tipos muy variados
        raise UnsupportedImageError(
            'No se pudo procesar la imagen. Prueba con otro formato (JPG o PNG).'
        ) from exc


def persist_jpeg(image_bytes: bytes, upload_dir: str) -> str:
    """Guarda un JPEG ya normalizado y devuelve su nombre de fichero."""
    filename = f'{uuid.uuid4().hex}.jpg'
    with open(os.path.join(upload_dir, filename), 'wb') as handle:
        handle.write(image_bytes)
    return filename
