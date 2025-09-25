import json
import numpy as np
import pandas as pd
from typing import Dict, Optional

from .limits import _active_limits_mg_l
from .cleaning import preprocess_timeseries


def compute_monthly_mi_from_timeseries(timeseries: Dict[str, Dict[str, float]]):
    if not timeseries:
        return {}
    # Build DataFrame: index=metal, columns=periods, values=mg/L
    metals = list(timeseries.keys())
    # union of all periods
    periods = sorted({p for m in metals for p in timeseries[m].keys()})
    df = pd.DataFrame(index=metals, columns=periods, dtype=float)
    for m, ser in timeseries.items():
        for p, v in ser.items():
            df.loc[m, p] = float(v)

    # Convert mg/L to µg/L (ppm ~ mg/L, multiply by 1000)
    df_ugL = df * 1000.0

    # Standards in µg/L; if only mg/L accessible, convert
    standards_mgL = _active_limits_mg_l()
    standards_ugL = {k: v * 1000.0 for k, v in standards_mgL.items()}

    # Step 1: per metal average across months
    df_ugL["Avg"] = df_ugL.mean(axis=1, skipna=True)

    # Step 2: MI_monthly = df.div(standards, axis=0).sum()
    # Use only metals that have a standard
    std_series = pd.Series(standards_ugL)
    aligned = df_ugL.drop(columns=["Avg"], errors="ignore")
    aligned = aligned[aligned.index.isin(std_series.index)]
    # avoid division by zero
    std_series = std_series.replace({0: np.nan})
    mi = aligned.div(std_series, axis=0).sum(axis=0, skipna=True)

    # Per-month dict and overall average across months
    per_month = {str(p): float(mi.get(p, np.nan)) for p in aligned.columns}
    overall_avg = float(mi.mean(skipna=True)) if len(mi) > 0 else float('nan')

    return {
        'per_month': per_month,
        'overall_avg': overall_avg,
    }



# --------------------------- HPI (Heavy Metal Pollution Index) ---------------------------

def _standards_series_mg_l(index_like) -> pd.Series:
    """Return standards S_i (mg/L) aligned to given index of metal aliases."""
    stds = pd.Series(_active_limits_mg_l())
    return stds.reindex(index_like)


def compute_q(C: pd.Series, S: pd.Series, I: Optional[pd.Series] = None) -> pd.Series:
    """Compute Q_i = ((C_i - I_i) / (S_i - I_i)) * 100 for aligned Series.

    - C: concentrations (mg/L)
    - S: standards (mg/L)
    - I: ideals/backgrounds (mg/L), broadcast or aligned; defaults to 0
    """
    if I is None:
        I = pd.Series(0.0, index=C.index)
    # Align indices
    C, S = C.align(S, join='inner')
    I = (I if isinstance(I, pd.Series) else pd.Series(I, index=C.index)).reindex(C.index)
    denom = (S - I).replace({0.0: np.nan})
    Q = ((C - I) / denom) * 100.0
    # Clean impossible values
    Q = Q.replace([np.inf, -np.inf], np.nan)
    return Q


def compute_w(S: pd.Series) -> pd.Series:
    """Compute weights W_i = 1 / S_i for standards S in mg/L."""
    W = 1.0 / S.replace({0.0: np.nan})
    return W


def compute_hpi(W: pd.Series, Q: pd.Series) -> float:
    """Compute HPI = sum(W_i * Q_i) / sum(W_i) for aligned Series."""
    W, Q = W.align(Q, join='inner')
    denom = W.sum(skipna=True)
    if pd.isna(denom) or denom == 0:
        return float('nan')
    return float((W * Q).sum(skipna=True) / denom)


def compute_hpi_from_metals(metals_mg_l: Dict[str, float], ideals_mg_l: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    """Compute HPI for a single sample given metals dict in mg/L.

    Returns a dict with keys: 'hpi', 'weights', 'Q'.
    """
    if not metals_mg_l:
        return {'hpi': float('nan')}
    C = pd.Series(metals_mg_l, dtype=float)
    S = _standards_series_mg_l(C.index)
    C = C[S.notna()]
    S = S.dropna()
    if ideals_mg_l:
        I = pd.Series(ideals_mg_l).reindex(S.index).fillna(0.0)
    else:
        I = pd.Series(0.0, index=S.index)
    C = C.reindex(S.index)
    Q = compute_q(C, S, I)
    W = compute_w(S)
    hpi_val = compute_hpi(W, Q)
    return {
        'hpi': hpi_val,
        'weights': W.to_dict(),
        'Q': Q.to_dict(),
    }


def compute_hpi_from_timeseries(
    timeseries: Dict[str, Dict[str, float]],
    ideals_mg_l: Optional[Dict[str, float]] = None,
    use_annual_average: bool = False,
    preprocess: bool = False,
    cleaning_kwargs: Optional[Dict] = None,
):
    """Compute HPI per period (e.g., per month) from a metal->period->value (mg/L) timeseries.

    - If use_annual_average=True, also compute HPI based on per-metal annual averages.
    Returns dict with 'per_month', 'overall_avg', and optionally 'annual_avg'.
    """
    if not timeseries:
        return {}
    if preprocess:
        timeseries = preprocess_timeseries(timeseries, **(cleaning_kwargs or {}))
    metals = list(timeseries.keys())
    periods = sorted({p for m in metals for p in timeseries[m].keys()})
    df = pd.DataFrame(index=metals, columns=periods, dtype=float)
    for m, ser in timeseries.items():
        for p, v in ser.items():
            df.loc[m, p] = float(v)

    # Standards aligned to metals present
    S = _standards_series_mg_l(df.index).dropna()
    if S.empty:
        return {}

    # Keep only metals with standards
    df = df[df.index.isin(S.index)]
    S = S.reindex(df.index)
    I = pd.Series(0.0, index=S.index)
    if ideals_mg_l:
        I = I.add(pd.Series(ideals_mg_l), fill_value=0.0).reindex(S.index).fillna(0.0)

    # Compute per-period HPI
    per_month = {}
    for period in df.columns:
        C = df[period].astype(float)
        Q = compute_q(C, S, I)
        W = compute_w(S)
        per_month[str(period)] = compute_hpi(W, Q)

    overall_avg = float(pd.Series(per_month).mean()) if per_month else float('nan')

    result = {
        'per_month': {k: float(v) for k, v in per_month.items()},
        'overall_avg': overall_avg,
    }

    if use_annual_average:
        C_avg = df.mean(axis=1, skipna=True)
        Q_avg = compute_q(C_avg, S, I)
        W = compute_w(S)
        result['annual_avg'] = compute_hpi(W, Q_avg)

    return result


# --------------------------- Contamination Degree (Cd) ---------------------------

def compute_cf(C: pd.Series, S: pd.Series) -> pd.Series:
    """Compute contamination factor Cfi = (C_i / C_ni) - 1 for aligned Series (mg/L)."""
    C, S = C.align(S, join='inner')
    S = S.replace({0.0: np.nan})
    Cf = (C / S) - 1.0
    return Cf.replace([np.inf, -np.inf], np.nan)


def compute_cd_from_metals(metals_mg_l: Dict[str, float]) -> Dict[str, float]:
    """Compute overall contamination degree Cd = sum(Cfi) for a single sample.

    Returns a dict with keys: 'cd', 'Cf'.
    """
    if not metals_mg_l:
        return {'cd': float('nan')}
    C = pd.Series(metals_mg_l, dtype=float)
    S = _standards_series_mg_l(C.index)
    C = C[S.notna()]
    S = S.dropna()
    C = C.reindex(S.index)
    Cf = compute_cf(C, S)
    cd_val = float(Cf.sum(skipna=True)) if not Cf.empty else float('nan')
    return {
        'cd': cd_val,
        'Cf': Cf.to_dict(),
    }


def compute_cd_from_timeseries(
    timeseries: Dict[str, Dict[str, float]],
    use_annual_average: bool = False,
    preprocess: bool = False,
    cleaning_kwargs: Optional[Dict] = None,
):
    """Compute Cd per period from a metal->period->value (mg/L) timeseries.

    Returns dict with 'per_month', 'overall_avg', and optionally 'annual_avg'.
    """
    if not timeseries:
        return {}
    if preprocess:
        timeseries = preprocess_timeseries(timeseries, **(cleaning_kwargs or {}))
    metals = list(timeseries.keys())
    periods = sorted({p for m in metals for p in timeseries[m].keys()})
    df = pd.DataFrame(index=metals, columns=periods, dtype=float)
    for m, ser in timeseries.items():
        for p, v in ser.items():
            df.loc[m, p] = float(v)

    S = _standards_series_mg_l(df.index).dropna()
    if S.empty:
        return {}
    df = df[df.index.isin(S.index)]
    S = S.reindex(df.index)

    per_month = {}
    for period in df.columns:
        C = df[period].astype(float)
        Cf = compute_cf(C, S)
        per_month[str(period)] = float(Cf.sum(skipna=True))

    overall_avg = float(pd.Series(per_month).mean()) if per_month else float('nan')

    result = {
        'per_month': per_month,
        'overall_avg': overall_avg,
    }

    if use_annual_average:
        C_avg = df.mean(axis=1, skipna=True)
        Cf_avg = compute_cf(C_avg, S)
        result['annual_avg'] = float(Cf_avg.sum(skipna=True)) if not Cf_avg.empty else float('nan')

    return result


# --------------------------- Heavy Metal Evaluation Index (HEI) ---------------------------

def compute_hei_terms(C: pd.Series, Hmax: pd.Series) -> pd.Series:
    """Compute HEI terms = C_i / Hmax_i for aligned Series (mg/L)."""
    C, Hmax = C.align(Hmax, join='inner')
    Hmax = Hmax.replace({0.0: np.nan})
    terms = C / Hmax
    return terms.replace([np.inf, -np.inf], np.nan)


def compute_hei_from_metals(metals_mg_l: Dict[str, float]) -> Dict[str, float]:
    """Compute HEI = sum(C_i / Hmax_i) for a single sample.

    Returns a dict with keys: 'hei', 'terms'.
    """
    if not metals_mg_l:
        return {'hei': float('nan')}
    C = pd.Series(metals_mg_l, dtype=float)
    Hmax = _standards_series_mg_l(C.index)
    C = C[Hmax.notna()]
    Hmax = Hmax.dropna()
    C = C.reindex(Hmax.index)
    terms = compute_hei_terms(C, Hmax)
    hei_val = float(terms.sum(skipna=True)) if not terms.empty else float('nan')
    return {
        'hei': hei_val,
        'terms': terms.to_dict(),
    }


def compute_hei_from_timeseries(
    timeseries: Dict[str, Dict[str, float]],
    use_annual_average: bool = False,
    preprocess: bool = False,
    cleaning_kwargs: Optional[Dict] = None,
):
    """Compute HEI per period from a metal->period->value (mg/L) timeseries.

    Returns dict with 'per_month', 'overall_avg', and optionally 'annual_avg'.
    """
    if not timeseries:
        return {}
    if preprocess:
        timeseries = preprocess_timeseries(timeseries, **(cleaning_kwargs or {}))
    metals = list(timeseries.keys())
    periods = sorted({p for m in metals for p in timeseries[m].keys()})
    df = pd.DataFrame(index=metals, columns=periods, dtype=float)
    for m, ser in timeseries.items():
        for p, v in ser.items():
            df.loc[m, p] = float(v)

    Hmax = _standards_series_mg_l(df.index).dropna()
    if Hmax.empty:
        return {}
    df = df[df.index.isin(Hmax.index)]
    Hmax = Hmax.reindex(df.index)

    per_month = {}
    for period in df.columns:
        C = df[period].astype(float)
        terms = compute_hei_terms(C, Hmax)
        per_month[str(period)] = float(terms.sum(skipna=True))

    overall_avg = float(pd.Series(per_month).mean()) if per_month else float('nan')

    result = {
        'per_month': per_month,
        'overall_avg': overall_avg,
    }

    if use_annual_average:
        C_avg = df.mean(axis=1, skipna=True)
        terms_avg = compute_hei_terms(C_avg, Hmax)
        result['annual_avg'] = float(terms_avg.sum(skipna=True)) if not terms_avg.empty else float('nan')

    return result


# --------------------------- Chronic Daily Intake (CDI) ---------------------------

def compute_cdi_terms(C: pd.Series, IR: float, EF: float, ED: float, BW: float, AT: Optional[float] = None) -> pd.Series:
    """Compute CDI per metal: CDI_i = (C_i * IR * EF * ED) / (BW * AT).

    Units:
    - C_i: mg/L
    - IR: L/day
    - EF: days/year
    - ED: years
    - BW: kg
    - AT: days (defaults to ED * 365)
    """
    if AT is None:
        AT = ED * 365.0
    denom = (BW * AT) if (BW and AT) else np.nan
    if denom == 0:
        denom = np.nan
    return (C.astype(float) * float(IR) * float(EF) * float(ED)) / denom


def compute_cdi_from_metals(
    metals_mg_l: Dict[str, float],
    IR: float = 2.0,
    EF: float = 365.0,
    ED: float = 30.0,
    BW: float = 70.0,
    AT: Optional[float] = None,
) -> Dict[str, float]:
    """Compute CDI for a single sample.

    Returns dict: 'cdi_total', 'cdi_by_metal'. Defaults are typical adult exposure assumptions.
    """
    if not metals_mg_l:
        return {'cdi_total': float('nan')}
    C = pd.Series(metals_mg_l, dtype=float)
    cdi = compute_cdi_terms(C, IR=IR, EF=EF, ED=ED, BW=BW, AT=AT)
    return {
        'cdi_total': float(cdi.sum(skipna=True)),
        'cdi_by_metal': cdi.to_dict(),
        'params': {'IR': IR, 'EF': EF, 'ED': ED, 'BW': BW, 'AT': (AT if AT is not None else ED * 365.0)},
    }


def compute_cdi_from_timeseries(
    timeseries: Dict[str, Dict[str, float]],
    IR: float = 2.0,
    EF: float = 365.0,
    ED: float = 30.0,
    BW: float = 70.0,
    AT: Optional[float] = None,
    use_annual_average: bool = False,
):
    """Compute CDI per period from a metal->period->value (mg/L) timeseries.

    Returns dict with 'per_month' (totals), 'overall_avg', and optionally 'annual_avg'.
    """
    if not timeseries:
        return {}
    metals = list(timeseries.keys())
    periods = sorted({p for m in metals for p in timeseries[m].keys()})
    df = pd.DataFrame(index=metals, columns=periods, dtype=float)
    for m, ser in timeseries.items():
        for p, v in ser.items():
            df.loc[m, p] = float(v)

    per_month = {}
    for period in df.columns:
        C = df[period].astype(float)
        cdi = compute_cdi_terms(C, IR=IR, EF=EF, ED=ED, BW=BW, AT=AT)
        per_month[str(period)] = float(cdi.sum(skipna=True))

    overall_avg = float(pd.Series(per_month).mean()) if per_month else float('nan')

    result = {
        'per_month': per_month,
        'overall_avg': overall_avg,
        'params': {'IR': IR, 'EF': EF, 'ED': ED, 'BW': BW, 'AT': (AT if AT is not None else ED * 365.0)},
    }

    if use_annual_average:
        C_avg = df.mean(axis=1, skipna=True)
        cdi_avg = compute_cdi_terms(C_avg, IR=IR, EF=EF, ED=ED, BW=BW, AT=AT)
        result['annual_avg'] = float(cdi_avg.sum(skipna=True))

    return result


# --------------------------- Hazard Quotient (HQ) and Hazard Index (HI) ---------------------------

def _default_rfd_mg_per_kg_day() -> Dict[str, float]:
    """Default reference doses (mg/kg·day) for common metals.

    Note: Values are indicative; provide overrides via rfd_overrides to use jurisdiction-specific values.
    """
    return {
        # Sources commonly cited in literature (EPA/ATSDR/WHO). Adjust as needed.
        "As": 0.0003,   # Arsenic
        "Cd": 0.001,    # Cadmium
        "Cr": 0.003,    # Chromium (assuming hexavalent; for Cr(III) typical 1.5)
        "Cu": 0.04,     # Copper
        "Ni": 0.02,     # Nickel
        "Zn": 0.3,      # Zinc
        "Mn": 0.14,     # Manganese (drinking water RfD proxy)
        "Fe": 0.7,      # Iron (screening value)
        "Hg": 0.0003,   # Mercury (inorganic)
        # Lead (Pb) typically lacks an EPA RfD; risk often modeled via BLL. Use with caution.
        "Pb": 0.0035,
    }


def _rfd_series(index_like, overrides: Optional[Dict[str, float]] = None) -> pd.Series:
    base = pd.Series(_default_rfd_mg_per_kg_day())
    if overrides:
        for k, v in overrides.items():
            base[k] = float(v)
    return base.reindex(index_like)


def compute_hq_terms(cdi_by_metal: pd.Series, rfd_overrides: Optional[Dict[str, float]] = None) -> pd.Series:
    """Compute HQ_i = CDI_i / RfD_i. CDI units mg/kg·day; RfD mg/kg·day."""
    RfD = _rfd_series(cdi_by_metal.index, overrides=rfd_overrides)
    RfD = RfD.replace({0.0: np.nan})
    HQ = cdi_by_metal.astype(float) / RfD
    return HQ.replace([np.inf, -np.inf], np.nan)


def compute_hq_from_metals(
    metals_mg_l: Dict[str, float],
    IR: float = 2.0,
    EF: float = 365.0,
    ED: float = 30.0,
    BW: float = 70.0,
    AT: Optional[float] = None,
    rfd_overrides: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """Compute per-metal HQ and total HI for a single sample using CDI and RfD."""
    cdi_res = compute_cdi_from_metals(metals_mg_l, IR=IR, EF=EF, ED=ED, BW=BW, AT=AT)
    cdi_series = pd.Series(cdi_res.get('cdi_by_metal', {}))
    if cdi_series.empty:
        return {'hi': float('nan')}
    HQ = compute_hq_terms(cdi_series, rfd_overrides=rfd_overrides)
    HI = float(HQ.sum(skipna=True)) if not HQ.empty else float('nan')
    return {
        'hi': HI,
        'hq_by_metal': HQ.to_dict(),
        'params': cdi_res.get('params', {}),
    }


def compute_hq_from_timeseries(
    timeseries: Dict[str, Dict[str, float]],
    IR: float = 2.0,
    EF: float = 365.0,
    ED: float = 30.0,
    BW: float = 70.0,
    AT: Optional[float] = None,
    rfd_overrides: Optional[Dict[str, float]] = None,
    use_annual_average: bool = False,
    preprocess: bool = False,
    cleaning_kwargs: Optional[Dict] = None,
):
    """Compute HI per period (sum of HQs) from a metal->period->value (mg/L) timeseries.

    Returns dict with 'per_month' (HI totals), 'overall_avg', and optionally 'annual_avg'.
    """
    if not timeseries:
        return {}
    if preprocess:
        timeseries = preprocess_timeseries(timeseries, **(cleaning_kwargs or {}))
    metals = list(timeseries.keys())
    periods = sorted({p for m in metals for p in timeseries[m].keys()})
    df = pd.DataFrame(index=metals, columns=periods, dtype=float)
    for m, ser in timeseries.items():
        for p, v in ser.items():
            df.loc[m, p] = float(v)

    per_month_hi = {}
    for period in df.columns:
        C = df[period].astype(float)
        cdi = compute_cdi_terms(C, IR=IR, EF=EF, ED=ED, BW=BW, AT=AT)
        HQ = compute_hq_terms(cdi, rfd_overrides=rfd_overrides)
        per_month_hi[str(period)] = float(HQ.sum(skipna=True))

    overall_avg = float(pd.Series(per_month_hi).mean()) if per_month_hi else float('nan')

    result = {
        'per_month': per_month_hi,
        'overall_avg': overall_avg,
        'params': {'IR': IR, 'EF': EF, 'ED': ED, 'BW': BW, 'AT': (AT if AT is not None else ED * 365.0)},
    }

    if use_annual_average:
        C_avg = df.mean(axis=1, skipna=True)
        cdi_avg = compute_cdi_terms(C_avg, IR=IR, EF=EF, ED=ED, BW=BW, AT=AT)
        HQ_avg = compute_hq_terms(cdi_avg, rfd_overrides=rfd_overrides)
        result['annual_avg'] = float(HQ_avg.sum(skipna=True))

    return result

