"""Geolocation lookup for source URLs."""

from __future__ import annotations

import logging
from functools import lru_cache
from socket import getaddrinfo
from typing import Optional
from urllib.parse import urlparse

from piratehunt.api.realtime.types import GeoLocation

logger = logging.getLogger(__name__)

# Fallback country codes for TLDs (best-effort guesses)
TLD_FALLBACK = {
    "in": ("IN", "India", 20.5937, 78.9629),
    "us": ("US", "United States", 37.0902, -95.7129),
    "uk": ("GB", "United Kingdom", 55.3781, -3.436),
    "ru": ("RU", "Russia", 61.524, 105.3188),
    "br": ("BR", "Brazil", -14.2350, -51.9253),
    "cn": ("CN", "China", 35.8617, 104.1954),
    "de": ("DE", "Germany", 51.1657, 10.4515),
    "fr": ("FR", "France", 46.2276, 2.2137),
    "jp": ("JP", "Japan", 36.2048, 138.2529),
    "mx": ("MX", "Mexico", 23.6345, -102.5528),
}

# Cache for DNS lookups and geolocation results
_location_cache: dict[str, GeoLocation] = {}


def _extract_host_from_url(url: str) -> str:
    """Extract hostname from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc or parsed.path.split("/")[0]
    except Exception as e:
        logger.warning(f"Failed to parse URL {url}: {e}")
        return "unknown"


def _get_country_from_tld(host: str) -> tuple[str, str, float, float]:
    """Get country code and coords from TLD (best-effort)."""
    try:
        # Extract TLD
        parts = host.split(".")
        tld = parts[-1].lower().rstrip(":")
        
        # Check fallback table
        if tld in TLD_FALLBACK:
            return TLD_FALLBACK[tld]
        
        # Default to India (common for piracy targets)
        return "IN", "India", 20.5937, 78.9629
    except Exception:
        return "IN", "India", 20.5937, 78.9629


@lru_cache(maxsize=1024)
def lookup_location(url: str) -> GeoLocation:
    """
    Lookup geolocation for a URL's host.
    
    Uses best-effort DNS + TLD matching. Falls back to country-level guesses.
    """
    # Check cache
    if url in _location_cache:
        return _location_cache[url]
    
    host = _extract_host_from_url(url)
    
    try:
        # Try DNS lookup first
        try:
            addr_info = getaddrinfo(host, None)
            # Successfully resolved — assume location unknown but valid host
            country_code, country_name, lat, lng = _get_country_from_tld(host)
        except Exception:
            # DNS failed — use TLD fallback
            country_code, country_name, lat, lng = _get_country_from_tld(host)
        
        location = GeoLocation(
            lat=lat,
            lng=lng,
            country=country_code,
            country_name=country_name,
            city=None,
        )
        
        _location_cache[url] = location
        return location
        
    except Exception as e:
        logger.warning(f"Geolocation lookup failed for {url}: {e}")
        # Final fallback: India
        location = GeoLocation(
            lat=20.5937,
            lng=78.9629,
            country="IN",
            country_name="India",
            city=None,
        )
        _location_cache[url] = location
        return location


def clear_location_cache() -> None:
    """Clear the location cache (useful for testing)."""
    _location_cache.clear()
