from typing import Dict, Optional

# BIS/WHO permissible limits for drinking water (mg/L)
# Values are illustrative; update as per authoritative standards.
BIS_WHO_LIMITS_MG_L: Dict[str, float] = {
    "As": 0.01,   # Arsenic
    "Cd": 0.003,  # Cadmium
    "Pb": 0.01,   # Lead
    "Hg": 0.006,  # Mercury (as inorganic)
    "Cr": 0.05,   # Chromium (total)
    "Ni": 0.07,   # Nickel
}


def get_limit_mg_l(metal_alias: str) -> Optional[float]:
    return BIS_WHO_LIMITS_MG_L.get(metal_alias)


def get_weight(metal_alias: str) -> Optional[float]:
    limit = get_limit_mg_l(metal_alias)
    if limit and limit > 0:
        return 1.0 / limit
    return None


def get_standard_id() -> str:
    # Return a version tag for the standards table; update when you revise limits
    return "BIS_WHO_v1"


