from typing import Dict, Optional, Tuple, Union

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


def timeseries_to_dataframe(timeseries: Dict[str, Dict[str, float]]) -> pd.DataFrame:
    """Convert metal->period->value timeseries to DataFrame (index=metals, columns=periods)."""
    if not timeseries:
        return pd.DataFrame()
    metals = list(timeseries.keys())
    periods = sorted({p for m in metals for p in timeseries[m].keys()})
    df = pd.DataFrame(index=metals, columns=periods, dtype=float)
    for m, ser in timeseries.items():
        for p, v in ser.items():
            try:
                df.loc[m, p] = float(v)
            except Exception:
                df.loc[m, p] = np.nan
    return df


def dataframe_to_timeseries(df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Convert DataFrame (index=metals, columns=periods) back to dict of dict."""
    out: Dict[str, Dict[str, float]] = {}
    for metal in df.index:
        out[str(metal)] = {str(p): (None if pd.isna(df.loc[metal, p]) else float(df.loc[metal, p])) for p in df.columns}
    return out


def preprocess_dataframe(
    df: pd.DataFrame,
    missing_threshold: float = 0.3,
    impute_strategy: str = 'auto',  # 'auto'|'mean'|'median'|'none'
    zscore_outlier_threshold: Optional[float] = 3.0,
    standardize: bool = False,
) -> pd.DataFrame:
    """Preprocess a metals x periods DataFrame:
    - Handle missing values: if missing fraction <= threshold, impute (mean/median); else drop row/column
    - Detect outliers via z-score across periods per metal; set outliers to NaN and re-impute
    - Optionally standardize using StandardScaler across periods (months x metals)
    """
    if df is None or df.empty:
        return df

    work = df.copy()

    # 1) Initial missing handling by rows (metals)
    row_missing_frac = work.isna().mean(axis=1)
    keep_rows = row_missing_frac <= 1.0  # keep all initially; we'll drop high-missing rows later

    # 2) Column-wise (periods) missing handling
    col_missing_frac = work.isna().mean(axis=0)
    # Drop columns with too many missing values
    drop_cols = col_missing_frac[col_missing_frac > missing_threshold].index.tolist()
    if drop_cols:
        work = work.drop(columns=drop_cols)

    # Recompute after column drop
    if work.empty:
        return work
    row_missing_frac = work.isna().mean(axis=1)
    # Drop rows (metals) with too many missing values
    drop_rows = row_missing_frac[row_missing_frac > missing_threshold].index.tolist()
    if drop_rows:
        work = work.drop(index=drop_rows)

    if work.empty:
        return work

    # Choose impute strategy
    if impute_strategy == 'auto':
        # Use median when data has outliers/heavy tails (robust). Here we default to median.
        impute_strategy_eff = 'median'
    else:
        impute_strategy_eff = impute_strategy

    # 3) Impute remaining missing values per metal
    if impute_strategy_eff in ('mean', 'median'):
        if impute_strategy_eff == 'mean':
            fill_values = work.mean(axis=1)
        else:
            fill_values = work.median(axis=1)
        for metal in work.index:
            work.loc[metal, :] = work.loc[metal, :].fillna(fill_values.loc[metal])

    # 4) Outlier detection via z-score across periods per metal
    if zscore_outlier_threshold is not None and zscore_outlier_threshold > 0:
        for metal in work.index:
            series = work.loc[metal, :]
            mean = series.mean()
            std = series.std(ddof=0)
            if std and std > 0:
                zscores = (series - mean) / std
                outlier_mask = zscores.abs() > zscore_outlier_threshold
                if outlier_mask.any():
                    work.loc[metal, outlier_mask] = np.nan
        # Re-impute after outlier removal
        if impute_strategy_eff in ('mean', 'median'):
            if impute_strategy_eff == 'mean':
                fill_values = work.mean(axis=1)
            else:
                fill_values = work.median(axis=1)
            for metal in work.index:
                work.loc[metal, :] = work.loc[metal, :].fillna(fill_values.loc[metal])

    # 5) Optional standardization
    if standardize:
        # X = months x metals; transpose then scale, then transpose back
        X = work.T.values  # shape: periods x metals
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        work = pd.DataFrame(X_scaled.T, index=work.index, columns=work.columns)

    return work


def preprocess_timeseries(
    timeseries: Dict[str, Dict[str, float]],
    missing_threshold: float = 0.3,
    impute_strategy: str = 'auto',
    zscore_outlier_threshold: Optional[float] = 3.0,
    standardize: bool = False,
) -> Dict[str, Dict[str, float]]:
    """Preprocess timeseries dict and return cleaned dict."""
    df = timeseries_to_dataframe(timeseries)
    if df.empty:
        return {}
    cleaned = preprocess_dataframe(
        df,
        missing_threshold=missing_threshold,
        impute_strategy=impute_strategy,
        zscore_outlier_threshold=zscore_outlier_threshold,
        standardize=standardize,
    )
    return dataframe_to_timeseries(cleaned)


