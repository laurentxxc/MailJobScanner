#!/usr/bin/env python3
"""
Commute calculation via OpenRouteService API.

Geocodes two addresses and returns travel time + distance
using ORS directions API.
"""
import logging

import requests

from config import resolve_env_var

logger = logging.getLogger(__name__)

ORS_GEOCODE_URL = "https://api.openrouteservice.org/geocode/search"
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/{profile}/json"

_PROFILE_MAP = {
    "driving": "driving-car",
    "cycling": "cycling-regular",
    "walking": "foot-walking",
}


def geocode(address: str, api_key: str) -> tuple[float, float] | None:
    """Geocode an address string into (latitude, longitude) via ORS."""
    try:
        resp = requests.get(
            ORS_GEOCODE_URL,
            params={"api_key": api_key, "text": address, "size": 1},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        features = data.get("features", [])
        if not features:
            logger.warning("No geocode results for '%s'", address)
            return None
        coords = features[0]["geometry"]["coordinates"]  # [lon, lat]
        return (coords[1], coords[0])  # return as (lat, lon)
    except Exception as e:
        logger.warning("Geocode failed for '%s': %s", address, e)
        return None


def _format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{int(seconds)} sec"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)} min"
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    if mins == 0:
        return f"{hours}h"
    return f"{hours}h{mins:02d}"


def get_commute_info(
    home_address: str,
    job_location: str,
    api_key: str,
    profile: str = "driving-car",
) -> str:
    """
    Calculate commute info between home and job location.
    Returns a string like "45 min (32 km)" or empty string on failure.
    """
    resolved_key = resolve_env_var(api_key) if api_key else None
    if not resolved_key:
        logger.warning("No ORS API key configured — skipping commute calculation")
        return ""

    if not job_location or job_location.lower() in ("remote", "unknown", ""):
        return ""

    home_coords = geocode(home_address, resolved_key)
    job_coords = geocode(job_location, resolved_key)

    if not home_coords or not job_coords:
        return ""

    ors_profile = _PROFILE_MAP.get(profile, profile)

    try:
        resp = requests.post(
            ORS_DIRECTIONS_URL.format(profile=ors_profile),
            headers={
                "Authorization": resolved_key,
                "Content-Type": "application/json",
            },
            json={
                "coordinates": [
                    [home_coords[1], home_coords[0]],  # ORS expects [lon, lat]
                    [job_coords[1], job_coords[0]],
                ]
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        segment = data["routes"][0]["summary"]
        duration = _format_duration(segment["duration"])
        distance_km = segment["distance"] / 1000

        return f"{duration} ({distance_km:.0f} km)"

    except Exception as e:
        logger.warning("Commute calculation failed: %s", e)
        return ""


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    key_env = "${OPENROUTESERVICE_API_KEY}"
    api_key = resolve_env_var(key_env)
    if not api_key:
        print("Set OPENROUTESERVICE_API_KEY in data/private/.env or env")
        sys.exit(1)

    if len(sys.argv) == 3:
        home, job = sys.argv[1], sys.argv[2]
    else:
        home = "Achères, Yvelines, France"
        job = sys.argv[1] if len(sys.argv) == 2 else "Paris, France"
        print(f"Usage: python -m core.llm.commute <job_location> [home_address]")
        print(f"Using defaults: home={home}, job={job}\n")

    print(f"Geocoding '{home}'...")
    h = geocode(home, api_key)
    print(f"  -> {h}")

    print(f"Geocoding '{job}'...")
    j = geocode(job, api_key)
    print(f"  -> {j}")

    if h and j:
        profile = sys.argv[3] if len(sys.argv) > 3 else "driving-car"
        result = get_commute_info(home, job, key_env, profile)
        print(f"\nCommute ({profile}): {result}")
    else:
        print("\nCould not geocode one or both addresses.")
