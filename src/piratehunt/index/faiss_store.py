from __future__ import annotations

import logging

import numpy as np

try:
    import faiss
except ImportError:
    faiss = None

from piratehunt.fingerprint.types import VisualFingerprint

logger = logging.getLogger(__name__)


class VisualHashIndex:
    """
    FAISS-based index for visual fingerprints (pHash and dHash).

    Converts 64-bit hex hashes to 64-dimensional binary vectors for L2 search.
    Hamming distance approximated via L2 distance on bit vectors.
    """

    def __init__(self, dimension: int = 64):
        """
        Initialize the visual hash index.

        Args:
            dimension: Bit dimension for hashes (default 64 for pHash/dHash)
        """
        if faiss is None:
            raise ImportError("faiss-cpu is required. Install with: pip install faiss-cpu")

        self.dimension = dimension
        self.index = faiss.IndexFlatL2(dimension)
        self.fingerprints: list[VisualFingerprint] = []
        logger.info(f"Initialized VisualHashIndex with dimension={dimension}")

    def _hex_to_bit_vector(self, hex_hash: str) -> np.ndarray:
        """
        Convert 64-bit hex hash to 64-dimensional float vector of {0, 1}.

        Args:
            hex_hash: Hex string representation of hash

        Returns:
            Float32 vector of length 64
        """
        # Remove '0x' prefix if present
        hex_str = hex_hash.lstrip("0x")
        # Pad to 16 hex chars (64 bits)
        hex_str = hex_str.zfill(16)

        # Convert hex to integer to binary
        hash_int = int(hex_str, 16)
        bit_vector = np.array(
            [(hash_int >> i) & 1 for i in range(self.dimension)], dtype=np.float32
        )
        return bit_vector

    def add(self, fingerprints: list[VisualFingerprint]) -> None:
        """
        Add visual fingerprints to the index.

        Args:
            fingerprints: List of VisualFingerprint objects
        """
        if not fingerprints:
            return

        vectors = []
        for fp in fingerprints:
            # Use pHash as primary; dhash could be added for multi-hash search
            phash_vector = self._hex_to_bit_vector(fp.phash)
            vectors.append(phash_vector)

        vectors_array = np.array(vectors, dtype=np.float32)
        self.index.add(vectors_array)
        self.fingerprints.extend(fingerprints)

        logger.debug(f"Added {len(fingerprints)} fingerprints to index. Total: {len(self)}")

    def search(
        self, query: VisualFingerprint, top_k: int = 5
    ) -> list[tuple[VisualFingerprint, float]]:
        """
        Search for similar visual fingerprints.

        Args:
            query: Query VisualFingerprint
            top_k: Number of top results to return

        Returns:
            List of (fingerprint, distance) tuples, sorted by distance (nearest first)
        """
        if len(self.fingerprints) == 0:
            logger.warning("Index is empty")
            return []

        query_vector = self._hex_to_bit_vector(query.phash).reshape(1, -1)
        distances, indices = self.index.search(query_vector, min(top_k, len(self.fingerprints)))

        results = []
        for idx, distance in zip(indices[0], distances[0], strict=False):
            if idx >= 0:  # Valid index
                results.append((self.fingerprints[int(idx)], float(distance)))

        nearest_dist = f"{results[0][1]:.4f}" if results else "N/A"
        logger.debug(
            f"Search returned {len(results)} results. Nearest distance: {nearest_dist}"
        )
        return results

    def __len__(self) -> int:
        """Return number of fingerprints in index."""
        return len(self.fingerprints)

    def save(self, path: str) -> None:
        """
        Save index to disk.

        Args:
            path: File path to save to
        """
        try:
            faiss.write_index(self.index, path)
            logger.info(f"Saved index to {path}")
        except Exception as e:
            logger.error(f"Failed to save index: {e}")
            raise

    def load(self, path: str) -> None:
        """
        Load index from disk.

        Args:
            path: File path to load from
        """
        try:
            self.index = faiss.read_index(path)
            logger.info(f"Loaded index from {path}")
        except Exception as e:
            logger.error(f"Failed to load index: {e}")
            raise
