from __future__ import annotations

import logging

import imagehash
from PIL import Image

from piratehunt.fingerprint.types import VisualFingerprint

logger = logging.getLogger(__name__)


def phash_image(img: Image.Image) -> str:
    """
    Compute perceptual hash (pHash) of an image.

    Args:
        img: PIL Image object

    Returns:
        64-bit pHash as hex string
    """
    hash_obj = imagehash.phash(img)
    return str(hash_obj)


def dhash_image(img: Image.Image) -> str:
    """
    Compute difference hash (dHash) of an image.

    Args:
        img: PIL Image object

    Returns:
        64-bit dHash as hex string
    """
    hash_obj = imagehash.dhash(img)
    return str(hash_obj)


def fingerprint_keyframes(
    images: list[Image.Image], source_id: str = "unknown", start_frame_index: int = 0
) -> list[VisualFingerprint]:
    """
    Generate visual fingerprints for a list of keyframe images.

    Args:
        images: List of PIL Image objects
        source_id: Identifier for the media source
        start_frame_index: Starting frame index for sequencing

    Returns:
        List of VisualFingerprint models
    """
    fingerprints = []
    for idx, img in enumerate(images):
        try:
            phash = phash_image(img)
            dhash = dhash_image(img)
            fp = VisualFingerprint(
                phash=phash,
                dhash=dhash,
                frame_index=start_frame_index + idx,
                source_id=source_id,
            )
            fingerprints.append(fp)
            logger.debug(
                f"Generated visual fingerprint for frame {start_frame_index + idx}:"
                f" phash={phash[:16]}..., dhash={dhash[:16]}..."
            )
        except Exception as e:
            logger.error(f"Failed to fingerprint image at index {idx}: {e}")
            continue

    return fingerprints
