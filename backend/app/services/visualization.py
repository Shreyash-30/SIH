import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from .limits import _active_limits_mg_l
from .indices import compute_hpi_from_timeseries, compute_hei_from_timeseries
from .indices import compute_hq_from_metals, compute_cdi_from_metals

sns.set(style="whitegrid")


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def save_fig(out_path: str, dpi: int = 180) -> str:
    plt.tight_layout()
    plt.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close()
    return out_path


# --------------------------- Step 1: Exceedances (Mean vs Limit) ---------------------------

def plot_exceedances_bar(means: Dict[str, float], title: str, out_path: str) -> str:
    """Bar chart comparing per-metal mean vs permissible limits.
    Colors indicate exceedances. Dashed red markers for limits.
    """
    if not means:
        return ""
    limits = _active_limits_mg_l()

    metals: List[str] = list(means.keys())
    mean_vals = [float(means[m]) if means[m] is not None else np.nan for m in metals]
    limit_vals = []
    for m in metals:
        lim = limits.get(m)
        if lim is None:
            for k, v in limits.items():
                if str(k).lower() == str(m).lower():
                    lim = v
                    break
        limit_vals.append(float(lim) if lim is not None else np.nan)

    df = pd.DataFrame({
        'Metal': metals,
        'Mean_mgL': mean_vals,
        'Limit_mgL': limit_vals,
    })
    df['Exceeds'] = df['Mean_mgL'] > df['Limit_mgL']

    plt.figure(figsize=(9, 5))
    palette = df['Exceeds'].map(lambda x: '#ef4444' if x else '#10b981')
    sns.barplot(x='Metal', y='Mean_mgL', data=df, palette=palette)
    # Plot per-metal limit markers as dashed lines
    for i, lim in enumerate(df['Limit_mgL']):
        if pd.notna(lim):
            plt.hlines(lim, i-0.4, i+0.4, colors='red', linestyles='--', linewidth=1.5)
    plt.title(title)
    plt.ylabel('Concentration (mg/L)')
    plt.xlabel('Metal')
    plt.legend(handles=[], labels=[])
    return save_fig(out_path)


# --------------------------- HPI Overall Gauge ---------------------------

def plot_hpi_overall_gauge(
    timeseries: Dict[str, Dict[str, float]],
    title: str,
    out_path: str,
    safe_thresh: float = 100.0,
    unsafe_thresh: float = 150.0,
) -> str:
    """Render a simple horizontal gauge for overall HPI with color-coded risk bands.

    Uses compute_hpi_from_timeseries(timeseries)['overall_avg'].
    Bands:
      [0, safe_thresh) -> green (Safe)
      [safe_thresh, unsafe_thresh) -> orange (Caution)
      [unsafe_thresh, +inf) -> red (Unsafe)
    """
    if not timeseries:
        return ""
    from .indices import compute_hpi_from_timeseries
    hpi = compute_hpi_from_timeseries(timeseries)
    overall = hpi.get('overall_avg')
    if overall is None or (isinstance(overall, float) and (pd.isna(overall))):
        return ""

    # Determine axis max to nicely fit value and thresholds
    max_val = float(max(unsafe_thresh * 1.5, (overall or 0) * 1.2, 200.0))

    plt.figure(figsize=(9, 2.2))
    ax = plt.gca()
    ax.set_xlim(0, max_val)
    ax.set_ylim(0, 1)
    ax.axis('off')

    # Draw bands
    ax.add_patch(plt.Rectangle((0, 0.15), min(safe_thresh, max_val), 0.7, color='#10b981', alpha=0.8))  # green
    if safe_thresh < max_val:
        ax.add_patch(plt.Rectangle((safe_thresh, 0.15), max(min(unsafe_thresh, max_val) - safe_thresh, 0), 0.7, color='#f59e0b', alpha=0.85))  # orange
    if unsafe_thresh < max_val:
        ax.add_patch(plt.Rectangle((unsafe_thresh, 0.15), max_val - unsafe_thresh, 0.7, color='#ef4444', alpha=0.85))  # red

    # Value marker
    x = float(max(0.0, min(overall, max_val)))
    ax.plot([x, x], [0.05, 0.95], color='#111827', linewidth=2.5)
    ax.scatter([x], [0.5], color='#111827', s=30, zorder=3)

    # Threshold labels
    ax.text(safe_thresh, 1.05, f"{safe_thresh:.0f}", ha='center', va='bottom', fontsize=10, color='#111827')
    ax.text(unsafe_thresh, 1.05, f"{unsafe_thresh:.0f}", ha='center', va='bottom', fontsize=10, color='#111827')

    # Title + value label
    risk = 'Safe' if overall < safe_thresh else ('Caution' if overall < unsafe_thresh else 'Unsafe')
    ax.text(max_val/2, 1.15, title, ha='center', va='bottom', fontsize=12, color='#111827')
    ax.text(x, 0.02, f"HPI={overall:.2f} ({risk})", ha='center', va='bottom', fontsize=11, color='#111827')

    return save_fig(out_path)

# --------------------------- Step 2: HPI monthly ---------------------------

def plot_hpi_monthly(timeseries: Dict[str, Dict[str, float]], title: str, out_path: str,
                      safe_thresh: float = 100.0, unsafe_thresh: float = 150.0) -> str:
    if not timeseries:
        return ""
    hpi = compute_hpi_from_timeseries(timeseries)
    per_month = hpi.get('per_month', {})
    if not per_month:
        return ""
    months = list(per_month.keys())
    values = [per_month[m] for m in months]

    def cat(v: float) -> str:
        if v < safe_thresh:
            return 'Safe'
        elif v < unsafe_thresh:
            return 'Caution'
        return 'Unsafe'

    categories = [cat(v) for v in values]
    color_map = {'Safe': 'green', 'Caution': 'orange', 'Unsafe': 'red'}
    colors = [color_map[c] for c in categories]

    plt.figure(figsize=(9, 5))
    sns.barplot(x=months, y=values, palette=colors)
    plt.axhline(safe_thresh, color='green', linestyle='--', label='Safe Threshold')
    plt.axhline(unsafe_thresh, color='red', linestyle='--', label='Unsafe Threshold')
    plt.title(title)
    plt.ylabel('HPI')
    plt.legend()
    return save_fig(out_path)


# --------------------------- Step 3: HEI and PLI monthly ---------------------------

def _compute_pli_per_month(timeseries: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """Compute PLI per month: (prod CF_i)^(1/n), CF_i = C_i / S_i."""
    if not timeseries:
        return {}
    # Build DataFrame metals x periods
    metals = list(timeseries.keys())
    periods = sorted({p for m in metals for p in timeseries[m].keys()})
    df = pd.DataFrame(index=metals, columns=periods, dtype=float)
    for m, ser in timeseries.items():
        for p, v in ser.items():
            try:
                df.loc[m, p] = float(v)
            except Exception:
                df.loc[m, p] = np.nan
    S = pd.Series(_active_limits_mg_l())
    S = S.reindex(df.index).replace({0.0: np.nan}).dropna()
    df = df[df.index.isin(S.index)]
    S = S.reindex(df.index)
    if df.empty or S.empty:
        return {}
    pli = {}
    for p in df.columns:
        C = df[p].astype(float)
        CF = (C / S).replace([np.inf, -np.inf], np.nan)
        CF = CF.dropna()
        if CF.empty:
            continue
        val = float(np.prod(CF) ** (1.0 / len(CF)))
        pli[str(p)] = val
    return pli


def plot_hei_pli_grouped(timeseries: Dict[str, Dict[str, float]], title: str, out_path: str,
                          hei_thresh: float = 5.0, pli_thresh: float = 1.0) -> str:
    if not timeseries:
        return ""
    hei = compute_hei_from_timeseries(timeseries)
    hei_pm = hei.get('per_month', {})
    pli_pm = _compute_pli_per_month(timeseries)
    months = sorted(set(hei_pm.keys()) | set(pli_pm.keys()))
    if not months:
        return ""
    data = []
    for m in months:
        data.append({'Month': m, 'Index': 'HEI', 'Value': float(hei_pm.get(m, np.nan))})
        data.append({'Month': m, 'Index': 'PLI', 'Value': float(pli_pm.get(m, np.nan))})
    df = pd.DataFrame(data)

    plt.figure(figsize=(10, 5))
    sns.barplot(x='Month', y='Value', hue='Index', data=df, palette=['orange', 'purple'])
    plt.axhline(hei_thresh, color='orange', linestyle='--', label='HEI Moderate Risk')
    plt.axhline(pli_thresh, color='purple', linestyle='--', label='PLI Threshold')
    plt.title(title)
    plt.ylabel('Index Value')
    plt.legend()
    return save_fig(out_path)


# --------------------------- Step 4: HQ per metal ---------------------------

def plot_hq_per_metal(metals_mg_l: Dict[str, float], title: str, out_path: str) -> str:
    if not metals_mg_l:
        return ""
    # Use CDI + RfD to get HQ by metal
    cdi = compute_cdi_from_metals(metals_mg_l)
    cdi_by = cdi.get('cdi_by_metal', {})
    if not cdi_by:
        return ""
    # Reuse HQ from compute_hq_from_metals for convenience
    hq = compute_hq_from_metals(metals_mg_l)
    hq_by = hq.get('hq_by_metal', {})
    metals = list(hq_by.keys())
    values = [hq_by[m] for m in metals]

    df = pd.DataFrame({'Metal': metals, 'HQ': values})
    df['Risk'] = df['HQ'].apply(lambda x: 'Unsafe' if x > 1 else 'Safe/Low')

    plt.figure(figsize=(9, 5))
    sns.barplot(x='Metal', y='HQ', data=df, hue='Risk', dodge=False, palette={'Safe/Low':'green','Unsafe':'red'})
    plt.axhline(1, color='red', linestyle='--', label='THQ Threshold')
    plt.title(title)
    plt.ylabel('HQ Value')
    plt.legend()
    return save_fig(out_path)
