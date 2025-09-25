import os
from typing import Dict, Optional

# Store authoritative permissible limits in µg/L as provided
# Sources (per user): WHO and BIS (IS 10500) recommendations
BIS_LIMITS_UG_L: Dict[str, float] = {
    "As": 10.0,     # Arsenic (As): 10 µg/L (BIS)
    "Pb": 10.0,     # Lead (Pb): 10 µg/L (BIS)
    "Cd": 3.0,      # Cadmium (Cd): 3 µg/L (BIS)
    "Cr": 50.0,     # Chromium (Cr): 50 µg/L (BIS)
    "Cu": 50.0,     # Copper (Cu): 50 µg/L (BIS recommended)
    "Fe": 300.0,    # Iron (Fe): 300 µg/L (BIS)
    "Mn": 100.0,    # Manganese (Mn): 100 µg/L (BIS)
    "Ni": 20.0,     # Nickel (Ni): 20 µg/L (BIS)
    "Zn": 5000.0,   # Zinc (Zn): 5000 µg/L (BIS)
}

WHO_LIMITS_UG_L: Dict[str, float] = {
    "As": 10.0,     # Arsenic (As): 10 µg/L (WHO)
    "Pb": 10.0,     # Lead (Pb): 10 µg/L (WHO)
    "Cd": 3.0,      # Cadmium (Cd): 3 µg/L (WHO)
    "Cr": 50.0,     # Chromium (Cr): 50 µg/L (WHO)
    "Cu": 2000.0,   # Copper (Cu): 2000 µg/L (WHO)
    "Zn": 5000.0,   # Zinc (Zn): 5000 µg/L (WHO)
    # WHO doesn't always set guideline values for Fe, Mn (often aesthetic); omit if unspecified
}


def _ugL_to_mgL_table(src: Dict[str, float]) -> Dict[str, float]:
    return {metal: (value / 1000.0) for metal, value in src.items()}


def _active_limits_mg_l() -> Dict[str, float]:
    # Choose source via env; default to BIS when available
    source = os.getenv("STANDARD_SOURCE", "BIS").upper()
    if source == "WHO":
        # Merge WHO with BIS where WHO missing (fallback), but prefer WHO values
        merged_ug = {**BIS_LIMITS_UG_L, **WHO_LIMITS_UG_L}
        merged_ug.update(WHO_LIMITS_UG_L)
        return _ugL_to_mgL_table(merged_ug)
    # BIS default
    return _ugL_to_mgL_table(BIS_LIMITS_UG_L)


def get_limit_mg_l(metal_alias: str) -> Optional[float]:
    return _active_limits_mg_l().get(metal_alias)


def get_weight(metal_alias: str) -> Optional[float]:
    limit = get_limit_mg_l(metal_alias)
    if limit and limit > 0:
        return 1.0 / limit
    return None


def get_standard_id() -> str:
    source = os.getenv("STANDARD_SOURCE", "BIS").upper()
    return f"{source}_v1"
