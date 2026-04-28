from __future__ import annotations

import logging
from typing import Optional

from piratehunt.fingerprint.types import AudioFingerprint

logger = logging.getLogger(__name__)


def _chromaprint_similarity(fp1: str, fp2: str) -> float:
    """
    Estimate similarity between two Chromaprint fingerprints.

    Simple comparison: count matching pairs of bits in hash strings.
    Returns similarity score between 0.0 and 1.0.

    Args:
        fp1: First fingerprint hash string
        fp2: Second fingerprint hash string

    Returns:
        Similarity score (0.0-1.0)
    """
    try:
        if not fp1 or not fp2:
            return 0.0

        # Parse fingerprints (often base64 encoded)
        # Simple approach: direct string similarity
        common = sum(1 for a, b in zip(fp1, fp2, strict=False) if a == b)
        max_len = max(len(fp1), len(fp2))

        if max_len == 0:
            return 1.0

        similarity = common / max_len
        return similarity
    except Exception:
        return 0.0


class AudioFingerprintStore:
    """
    In-memory store for audio fingerprints using Chromaprint similarity.

    Supports adding fingerprints and searching by similarity using simple
    string-based comparison. Phase 1 uses in-memory list; Phase 2 will migrate to pgvector.
    """

    def __init__(self):
        """Initialize empty audio fingerprint store."""
        self.fingerprints: list[AudioFingerprint] = []
        logger.info("Initialized AudioFingerprintStore")

    def add(self, fingerprints: list[AudioFingerprint]) -> None:
        """
        Add audio fingerprints to the store.

        Args:
            fingerprints: List of AudioFingerprint objects
        """
        if not fingerprints:
            return

        self.fingerprints.extend(fingerprints)
        logger.debug(
            f"Added {len(fingerprints)} audio fingerprints. Total: {len(self.fingerprints)}"
        )

    def search(
        self, query: AudioFingerprint, threshold: float = 0.85, top_k: Optional[int] = None
    ) -> list[tuple[AudioFingerprint, float]]:
        """
        Search for similar audio fingerprints.

        Uses simple string-based similarity comparison on fingerprint hashes.

        Args:
            query: Query AudioFingerprint
            threshold: Minimum similarity score (0.0-1.0) to return results
            top_k: If set, return only top_k results; otherwise return all above threshold

        Returns:
            List of (fingerprint, similarity_score) tuples, sorted by score (highest first)
        """
        if not self.fingerprints:
            logger.warning("Store is empty")
            return []

        results = []

        for fp in self.fingerprints:
            try:
                similarity = _chromaprint_similarity(query.fingerprint_hash, fp.fingerprint_hash)

                if similarity >= threshold:
                    results.append((fp, similarity))
            except Exception as e:
                logger.debug(f"Failed to compare fingerprints: {e}")
                continue

        # Sort by similarity (highest first)
        results.sort(key=lambda x: x[1], reverse=True)

        if top_k is not None:
            results = results[:top_k]

        best_match = f"{results[0][1]:.4f}" if results else "N/A"
        logger.debug(
            f"Search returned {len(results)} results above threshold {threshold}. "
            f"Best match: {best_match}"
        )

        return results

    def __len__(self) -> int:
        """Return number of fingerprints in store."""
        return len(self.fingerprints)

    def clear(self) -> None:
        """Clear all fingerprints from store."""
        self.fingerprints.clear()
        logger.debug("Cleared audio fingerprint store")
