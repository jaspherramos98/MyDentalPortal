# File: MyDentalPortal/blueprints/utils/images.py
# Shrink uploaded images before they're stored.
#
# Phone photos arrive at full camera resolution (avg 1.6 MB, up to 3+ MB in
# prod on 2026-09-26) and were ~95% of all database storage. Downscaling to what
# the app actually displays cuts that 5-10x. Runs AFTER upload validation
# (extension + magic bytes + decode-verify) — never instead of it.

import io
import logging

from PIL import Image, ImageOps

log = logging.getLogger(__name__)

# Longest side, in pixels. Photos show as a small avatar and at 1.2" in the
# patient PDF; documents (prescriptions, photographed X-rays) must stay legible.
PHOTO_MAX_SIDE = 800
DOCUMENT_MAX_SIDE = 2000
LOSSY_QUALITY = 82

# Formats we decode + re-encode, by extension. Everything else (HEIC — no
# decoder installed — PDFs, office docs) is stored untouched.
_FORMATS = {'jpg': 'JPEG', 'jpeg': 'JPEG', 'png': 'PNG', 'webp': 'WEBP'}


def shrink_image(data, ext, max_side):
    """Return ``data`` downscaled to ``max_side`` px (longest side) and re-encoded.

    * Never enlarges; keeps the same format (PNG stays lossless).
    * Applies the camera's EXIF rotation, then drops ALL metadata — including
      GPS location, which a phone photo of a patient must not carry.
    * Non-image types, and anything Pillow can't process, come back unchanged
      (they already passed validation, so storing the original is safe).
    """
    fmt = _FORMATS.get((ext or '').lower())
    if fmt is None:
        return data
    try:
        with Image.open(io.BytesIO(data)) as original:
            img = ImageOps.exif_transpose(original)
            img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            if fmt == 'JPEG' and img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')          # CMYK / RGBA / palette -> JPEG-safe
            out = io.BytesIO()
            options = {'optimize': True}
            if fmt in ('JPEG', 'WEBP'):
                options['quality'] = LOSSY_QUALITY
            img.save(out, fmt, **options)         # no exif= -> metadata dropped
            return out.getvalue()
    except Exception:
        log.exception("Image shrink failed; storing the validated original")
        return data
