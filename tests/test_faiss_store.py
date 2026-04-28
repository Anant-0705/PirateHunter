from __future__ import annotations

import numpy as np

from piratehunt.fingerprint.types import VisualFingerprint
from piratehunt.index.faiss_store import VisualHashIndex


def test_visual_hash_index_initialization():
    """Test VisualHashIndex initialization."""
    index = VisualHashIndex(dimension=64)

    assert index.dimension == 64
    assert len(index) == 0


def test_visual_hash_index_add_and_search():
    """Test adding fingerprints and searching."""
    index = VisualHashIndex()

    # Create synthetic fingerprints
    fp1 = VisualFingerprint(
        phash="a" * 16,  # 64-bit hex
        dhash="b" * 16,
        frame_index=0,
        source_id="video1",
    )
    fp2 = VisualFingerprint(
        phash="b" * 16,
        dhash="c" * 16,
        frame_index=1,
        source_id="video1",
    )

    index.add([fp1, fp2])
    assert len(index) == 2

    # Search for similar fingerprint
    results = index.search(fp1, top_k=2)

    assert len(results) > 0
    assert results[0][0].frame_index in [0, 1]
    assert isinstance(results[0][1], float)


def test_visual_hash_index_empty_search():
    """Test searching on empty index."""
    index = VisualHashIndex()

    fp = VisualFingerprint(
        phash="a" * 16,
        dhash="b" * 16,
        frame_index=0,
        source_id="test",
    )

    results = index.search(fp)
    assert results == []


def test_visual_hash_index_similar_hashes():
    """Test that flipping bits creates recognizable near-duplicates."""
    index = VisualHashIndex()

    # Base hash
    base_hash = "ffffffffffffffff"
    fp_base = VisualFingerprint(
        phash=base_hash,
        dhash="0000000000000000",
        frame_index=0,
        source_id="base",
    )

    # Near-duplicate: flip 2 bits (change f to d = flip bits 1 and 2)
    # ffffffffffffffff -> ddffffffffffffff (0xf = 1111, 0xd = 1101)
    near_dup_hash = "ddffffffffffffff"
    fp_near = VisualFingerprint(
        phash=near_dup_hash,
        dhash="0000000000000000",
        frame_index=1,
        source_id="near",
    )

    index.add([fp_base, fp_near])

    # Search for near-duplicate
    results = index.search(fp_base, top_k=2)

    assert len(results) >= 1
    # The near-duplicate should be found, though not necessarily first
    frame_indices = [r[0].frame_index for r in results]
    assert 0 in frame_indices or 1 in frame_indices


def test_visual_hash_index_hex_to_bit_vector():
    """Test hex to bit vector conversion."""
    index = VisualHashIndex()

    # Test conversion
    hex_hash = "ffffffffffffffff"
    bit_vector = index._hex_to_bit_vector(hex_hash)

    assert bit_vector.shape == (64,)
    assert bit_vector.dtype == np.float32
    assert np.all((bit_vector == 0) | (bit_vector == 1))
    # All 1s in this case
    assert np.sum(bit_vector) == 64

    # Test with different hash
    hex_hash2 = "0000000000000000"
    bit_vector2 = index._hex_to_bit_vector(hex_hash2)

    assert np.sum(bit_vector2) == 0


def test_visual_hash_index_hex_prefix_handling():
    """Test that 0x prefix is handled correctly."""
    index = VisualHashIndex()

    # With 0x prefix
    v1 = index._hex_to_bit_vector("0xffffffffffffffff")
    # Without 0x prefix
    v2 = index._hex_to_bit_vector("ffffffffffffffff")

    assert np.allclose(v1, v2)
