import math
from typing import Dict, Tuple

import numpy as np

from .limits import get_limit_mg_l, get_weight, get_standard_id


def compute_per_metal_terms(concentrations: Dict[str, float]) -> Tuple[Dict[str, Dict[str, float]], Dict[str, float]]:
    per_metal: Dict[str, Dict[str, float]] = {}
    weights: Dict[str, float] = {}
    for metal, c in (concentrations or {}).items():
        if c is None or (isinstance(c, float) and np.isnan(c)):
            continue
        s = get_limit_mg_l(metal)
        if s is None or s <= 0:
            continue
        w = get_weight(metal) or 0.0
        q = ((c - 0.0) / (s - 0.0)) * 100.0  # ideal I_i = 0 for heavy metals
        cf = c / s
        per_metal[metal] = {
            "C_i": float(c),
            "S_i": float(s),
            "Q_i": float(q),
            "W_i": float(w),
            "CF_i": float(cf),
        }
        weights[metal] = float(w)
    return per_metal, weights


def safe_geometric_mean(values):
    vals = [v for v in values if v is not None and v > 0]
    if not vals:
        return None
    return float(math.exp(sum(math.log(v) for v in vals) / len(vals)))


def compute_indices(concentrations: Dict[str, float]) -> Dict[str, float]:
    per_metal, weights = compute_per_metal_terms(concentrations)
    if not per_metal:
        return {"hpi": None, "hei": None, "pli": None, "cd_value": None, "num_metals": 0, "standard_id": get_standard_id()}

    # HPI
    num = sum(pm["Q_i"] * pm["W_i"] for pm in per_metal.values())
    den = sum(pm["W_i"] for pm in per_metal.values())
    hpi = float(num / den) if den > 0 else None

    # HEI
    hei = float(sum(pm["C_i"] / pm["S_i"] for pm in per_metal.values()))

    # PLI (geometric mean of CF_i)
    pli = safe_geometric_mean([pm["CF_i"] for pm in per_metal.values()])

    # Cd (degree of contamination) using sum(CF_i - 1)
    cd_value = float(sum(pm["CF_i"] - 1.0 for pm in per_metal.values()))

    return {
        "hpi": hpi,
        "hei": hei,
        "pli": pli,
        "cd_value": cd_value,
        "num_metals": len(per_metal),
        "standard_id": get_standard_id(),
    }


