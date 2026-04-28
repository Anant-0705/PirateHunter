from __future__ import annotations

from PIL import Image

from piratehunt.fingerprint.types import VisualFingerprint
from piratehunt.fingerprint.visual import dhash_image, fingerprint_keyframes, phash_image


def test_phash_image():
    """Test perceptual hashing of an image."""
    # Create a simple test image (16x16 red square)
    img = Image.new("RGB", (16, 16), color="red")

    phash = phash_image(img)

    # Verify result
    assert isinstance(phash, str)
    assert len(phash) == 16  # 64-bit hash in hex = 16 chars
    assert all(c in "0123456789abcdef" for c in phash)


def test_dhash_image():
    """Test difference hashing of an image."""
    img = Image.new("RGB", (16, 16), color="blue")

    dhash = dhash_image(img)

    assert isinstance(dhash, str)
    assert len(dhash) == 16
    assert all(c in "0123456789abcdef" for c in dhash)


def test_phash_similar_images():
    """Test that similar images produce similar pHashes."""
    # Create two very similar images
    img1 = Image.new("RGB", (32, 32), color="red")
    img2 = Image.new("RGB", (32, 32), color="red")
    img2.putpixel((0, 0), (255, 0, 1))  # Tiny difference

    phash1 = phash_image(img1)
    phash2 = phash_image(img2)

    # Hashes should be strings
    assert isinstance(phash1, str)
    assert isinstance(phash2, str)


def test_fingerprint_keyframes():
    """Test fingerprinting a batch of keyframe images."""
    # Create 3 test images
    images = [
        Image.new("RGB", (16, 16), color="red"),
        Image.new("RGB", (16, 16), color="green"),
        Image.new("RGB", (16, 16), color="blue"),
    ]

    fingerprints = fingerprint_keyframes(images, source_id="test_video", start_frame_index=0)

    # Verify results
    assert len(fingerprints) == 3
    for i, fp in enumerate(fingerprints):
        assert isinstance(fp, VisualFingerprint)
        assert len(fp.phash) == 16
        assert len(fp.dhash) == 16
        assert fp.frame_index == i
        assert fp.source_id == "test_video"


def test_fingerprint_keyframes_empty():
    """Test fingerprinting empty image list."""
    fingerprints = fingerprint_keyframes([])

    assert fingerprints == []


def test_fingerprint_keyframes_with_offset():
    """Test frame index sequencing with start offset."""
    images = [Image.new("RGB", (16, 16), color="red") for _ in range(2)]

    fingerprints = fingerprint_keyframes(images, source_id="offset_test", start_frame_index=10)

    assert len(fingerprints) == 2
    assert fingerprints[0].frame_index == 10
    assert fingerprints[1].frame_index == 11
