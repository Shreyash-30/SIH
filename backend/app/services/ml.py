import os
import json
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
from scipy import stats as spstats
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier, GradientBoostingRegressor
from sklearn.cluster import KMeans
from sklearn.metrics import mean_absolute_error, r2_score, accuracy_score, f1_score
from sklearn.preprocessing import PolynomialFeatures
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from joblib import dump
try:
    import folium
    from folium import plugins as folium_plugins
except Exception:
    folium = None
    folium_plugins = None
try:
    from staticmap import StaticMap, CircleMarker
except Exception:
    StaticMap = None
    CircleMarker = None
import logging
logger = logging.getLogger(__name__)

from ..models import Sample, MetalConcentration, MetalTimeSeries
from ..database import get_db
from .indices import (
    compute_hpi_from_metals,
    compute_cd_from_metals,
    compute_hei_from_metals,
    compute_cdi_from_metals,
    compute_hq_from_metals,
    compute_monthly_mi_from_timeseries,
)
from .stats import describe_series


# Resolve storage dir relative to this file's backend folder by default
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DEFAULT_STORAGE_DIR = os.path.join(_BACKEND_DIR, "storage", "ml")
STORAGE_DIR = os.getenv("ML_STORAGE_DIR", _DEFAULT_STORAGE_DIR)
os.makedirs(STORAGE_DIR, exist_ok=True)


def _collect_sample_timeseries(db, sample_id: int) -> Dict[str, Dict[str, float]]:
    rows = db.query(MetalTimeSeries).filter(MetalTimeSeries.sample_id == sample_id).all()
    ts: Dict[str, Dict[str, float]] = {}
    for r in rows:
        ts.setdefault(r.metal, {})[str(r.period)] = float(r.value_mg_l) if r.value_mg_l is not None else np.nan
    return ts


def _collect_sample_metals(db, sample_id: int) -> Dict[str, float]:
    rows = db.query(MetalConcentration).filter(MetalConcentration.sample_id == sample_id).all()
    return {r.metal: float(r.value_mg_l) if r.value_mg_l is not None else np.nan for r in rows}


def _indices_for_sample(metals: Dict[str, float], timeseries: Optional[Dict[str, Dict[str, float]]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if metals:
        try:
            out["HPI"] = float(compute_hpi_from_metals(metals).get("hpi", np.nan))
        except Exception:
            out["HPI"] = np.nan
        try:
            out["Cd"] = float(compute_cd_from_metals(metals).get("cd", np.nan))
        except Exception:
            out["Cd"] = np.nan
        try:
            out["HEI"] = float(compute_hei_from_metals(metals).get("hei", np.nan))
        except Exception:
            out["HEI"] = np.nan
        try:
            out["CDI"] = float(compute_cdi_from_metals(metals).get("cdi_total", np.nan))
        except Exception:
            out["CDI"] = np.nan
        try:
            out["HI"] = float(compute_hq_from_metals(metals).get("hi", np.nan))
        except Exception:
            out["HI"] = np.nan
    # MI uses timeseries; use overall_avg if available
    if timeseries:
        try:
            mi = compute_monthly_mi_from_timeseries(timeseries)
            out["MI"] = float(mi.get("overall_avg", np.nan))
        except Exception:
            out["MI"] = np.nan
    else:
        out.setdefault("MI", np.nan)
    return out


def _descriptive_stats_features(timeseries: Optional[Dict[str, Dict[str, float]]]) -> Dict[str, float]:
    """Build descriptive stats features from month-wise series per metal.

    For each metal with time series, compute mean/median/var/skew and average them across metals
    to produce compact features. This avoids exploding feature dimension.
    """
    features: Dict[str, float] = {}
    if not timeseries:
        return {"stats_mean": np.nan, "stats_median": np.nan, "stats_var": np.nan, "stats_skew": np.nan}
    means = []
    medians = []
    variances = []
    skews = []
    for metal, ser in timeseries.items():
        vals = [v for v in ser.values() if v is not None and np.isfinite(v)]
        if len(vals) == 0:
            continue
        d = describe_series(vals)
        means.append(d.get("mean", np.nan))
        medians.append(d.get("median", np.nan))
        variances.append(d.get("var", np.nan))
        skews.append(d.get("skew", np.nan))
    def _safe_mean(arr):
        arr = [x for x in arr if x is not None and np.isfinite(x)]
        return float(np.mean(arr)) if arr else np.nan
    features["stats_mean"] = _safe_mean(means)
    features["stats_median"] = _safe_mean(medians)
    features["stats_var"] = _safe_mean(variances)
    features["stats_skew"] = _safe_mean(skews)
    return features


def _correlation_meta(timeseries: Optional[Dict[str, Dict[str, float]]]) -> Dict[str, float]:
    """Compute within-sample correlations across months between metals and reduce to meta-features.

    Returns average absolute Pearson and Spearman correlations.
    """
    if not timeseries:
        return {"corr_pearson_mean_abs": np.nan, "corr_spearman_mean_abs": np.nan}
    metals = list(timeseries.keys())
    # Build union months
    months = sorted({m for ser in timeseries.values() for m in ser.keys()})
    if len(months) < 2 or len(metals) < 2:
        return {"corr_pearson_mean_abs": np.nan, "corr_spearman_mean_abs": np.nan}
    # Build matrix metals x months
    mat = []
    for metal in metals:
        row = []
        for mm in months:
            v = timeseries.get(metal, {}).get(mm, np.nan)
            try:
                row.append(float(v) if v is not None else np.nan)
            except Exception:
                row.append(np.nan)
        mat.append(row)
    X = np.array(mat, dtype=float)
    # Drop columns (months) where all NaN
    valid_cols = ~np.all(~np.isfinite(X), axis=0)
    X = X[:, valid_cols]
    if X.shape[1] < 2:
        return {"corr_pearson_mean_abs": np.nan, "corr_spearman_mean_abs": np.nan}
    # Compute pairwise correlations
    pearson_vals: List[float] = []
    spearman_vals: List[float] = []
    for i in range(len(metals)):
        for j in range(i + 1, len(metals)):
            xi = X[i, :]
            xj = X[j, :]
            mask = np.isfinite(xi) & np.isfinite(xj)
            if mask.sum() >= 3:
                try:
                    r, _ = spstats.pearsonr(xi[mask], xj[mask])
                    pearson_vals.append(abs(float(r)))
                except Exception:
                    pass
                try:
                    r_s, _ = spstats.spearmanr(xi[mask], xj[mask])
                    spearman_vals.append(abs(float(r_s)))
                except Exception:
                    pass
    def _safe_mean(arr):
        arr = [x for x in arr if x is not None and np.isfinite(x)]
        return float(np.mean(arr)) if arr else np.nan
    return {
        "corr_pearson_mean_abs": _safe_mean(pearson_vals),
        "corr_spearman_mean_abs": _safe_mean(spearman_vals),
    }


def assemble_dataset(db) -> pd.DataFrame:
    """Build a per-sample feature matrix combining raw metals, indices, descriptive stats, and correlation meta-features.

    Rows: samples; Columns: features.
    """
    samples = db.query(Sample).all()
    records: List[Dict[str, float]] = []
    for s in samples:
        row: Dict[str, float] = {"sample_id": int(s.id)}
        metals = _collect_sample_metals(db, s.id)
        # raw metals prefix
        for k, v in metals.items():
            row[f"metal_{k}"] = float(v) if v is not None else np.nan
        # time series (optional)
        ts = _collect_sample_timeseries(db, s.id)
        # indices
        idx = _indices_for_sample(metals, ts if ts else None)
        row.update({f"idx_{k}": v for k, v in idx.items()})
        # descriptive stats (over months if available)
        row.update(_descriptive_stats_features(ts if ts else None))
        # correlation meta
        row.update(_correlation_meta(ts if ts else None))
        records.append(row)
    df = pd.DataFrame.from_records(records).set_index("sample_id")
    return df


def _target_from_df(df: pd.DataFrame, target: str) -> pd.Series:
    key = target.upper()
    col = f"idx_{key}"
    if col in df.columns:
        return df[col]
    raise ValueError(f"Target '{target}' not found in computed indices. Available: {[c.replace('idx_','') for c in df.columns if c.startswith('idx_')]}")


def _class_from_target(y: pd.Series, target: str) -> pd.Series:
    t = target.upper()
    if t == "HPI":
        # Example thresholds; adjust as needed
        # Safe: <= 50, Moderate: (50, 100], Unsafe: > 100
        labels = []
        for v in y.fillna(np.nan):
            if not np.isfinite(v):
                labels.append(np.nan)
            elif v <= 50:
                labels.append("Safe")
            elif v <= 100:
                labels.append("Moderate")
            else:
                labels.append("Unsafe")
        return pd.Series(labels, index=y.index)
    # Default binary: median split
    median = np.nanmedian(y.values)
    return pd.Series(["Low" if (np.isfinite(v) and v <= median) else ("High" if np.isfinite(v) else np.nan) for v in y.values], index=y.index)


def train_regressors(db, target: str = "HPI", test_size: float = 0.2, random_state: int = 42, save_prefix: Optional[str] = None) -> Dict[str, Dict]:
    df = assemble_dataset(db)
    y = _target_from_df(df, target)
    X = df.drop(columns=[c for c in df.columns if c.startswith("idx_") and c.endswith(target.upper())]) if f"idx_{target.upper()}" in df.columns else df.copy()
    # Drop rows with NaN in y
    mask = np.isfinite(y.values)
    X = X.loc[mask]
    y = y.loc[mask]
    # Fill remaining NaNs in X with column means
    X = X.apply(lambda col: col.fillna(col.mean()))

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_state)

    results: Dict[str, Dict] = {}

    # Linear Regression
    lin = LinearRegression()
    lin.fit(X_train, y_train)
    y_pred_lin = lin.predict(X_test)
    results["linear_regression"] = {
        "mae": float(mean_absolute_error(y_test, y_pred_lin)),
        "r2": float(r2_score(y_test, y_pred_lin)),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
    }

    # Random Forest Regressor
    rf = RandomForestRegressor(n_estimators=300, random_state=random_state)
    rf.fit(X_train, y_train)
    y_pred_rf = rf.predict(X_test)
    results["random_forest_regressor"] = {
        "mae": float(mean_absolute_error(y_test, y_pred_rf)),
        "r2": float(r2_score(y_test, y_pred_rf)),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "feature_importances": {str(k): float(v) for k, v in zip(X.columns, rf.feature_importances_)}
    }

    # Persist models and artifacts
    prefix = save_prefix or target.upper()
    dump(lin, os.path.join(STORAGE_DIR, f"reg_lin_{prefix}.joblib"))
    dump(rf, os.path.join(STORAGE_DIR, f"reg_rf_{prefix}.joblib"))
    X_test.to_csv(os.path.join(STORAGE_DIR, f"reg_Xtest_{prefix}.csv"))
    pd.DataFrame({"y_test": y_test, "y_pred_lin": y_pred_lin, "y_pred_rf": y_pred_rf}, index=y_test.index).to_csv(
        os.path.join(STORAGE_DIR, f"reg_eval_{prefix}.csv")
    )
    with open(os.path.join(STORAGE_DIR, f"reg_results_{prefix}.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Plot and save feature importances for Random Forest Regressor
    try:
        _plot_feature_importances(
            results["random_forest_regressor"].get("feature_importances", {}),
            title=f"Feature Importance (RandomForest Regressor - {prefix})",
            filename=os.path.join(STORAGE_DIR, f"reg_rf_feature_importance_{prefix}.png"),
        )
    except Exception:
        # plotting should not break training pipeline
        pass

    return results


def train_classifier(db, target: str = "HPI", test_size: float = 0.2, random_state: int = 42, save_prefix: Optional[str] = None) -> Dict[str, Dict]:
    df = assemble_dataset(db)
    y_cont = _target_from_df(df, target)
    y = _class_from_target(y_cont, target)
    X = df.copy()
    # Remove explicit target columns to avoid leakage
    drop_cols = [c for c in X.columns if c.startswith("idx_") and c.endswith(target.upper())]
    if drop_cols:
        X = X.drop(columns=drop_cols)
    # Drop rows with NaN label
    mask = y.notna().values
    X = X.loc[mask]
    y = y.loc[mask]
    # Fill NaNs
    X = X.apply(lambda col: col.fillna(col.mean()))

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=y)

    clf = RandomForestClassifier(n_estimators=300, random_state=random_state, class_weight="balanced")
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)

    acc = float(accuracy_score(y_test, y_pred))
    f1 = float(f1_score(y_test, y_pred, average="weighted"))

    results = {
        "random_forest_classifier": {
            "accuracy": acc,
            "f1_weighted": f1,
            "n_train": int(len(X_train)),
            "n_test": int(len(X_test)),
            "feature_importances": {str(k): float(v) for k, v in zip(X.columns, clf.feature_importances_)}
        }
    }

    prefix = save_prefix or f"CLS_{target.upper()}"
    dump(clf, os.path.join(STORAGE_DIR, f"clf_rf_{prefix}.joblib"))
    X_test.to_csv(os.path.join(STORAGE_DIR, f"clf_Xtest_{prefix}.csv"))
    pd.DataFrame({"y_test": y_test, "y_pred": y_pred}, index=y_test.index).to_csv(
        os.path.join(STORAGE_DIR, f"clf_eval_{prefix}.csv")
    )
    with open(os.path.join(STORAGE_DIR, f"clf_results_{prefix}.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Plot and save feature importances for Random Forest Classifier
    try:
        _plot_feature_importances(
            results["random_forest_classifier"].get("feature_importances", {}),
            title=f"Feature Importance (RandomForest Classifier - {prefix})",
            filename=os.path.join(STORAGE_DIR, f"clf_rf_feature_importance_{prefix}.png"),
        )
    except Exception:
        pass

    return results


def run_kmeans(db, k: int = 3, random_state: int = 42, save_prefix: Optional[str] = None) -> Dict[str, Dict]:
    """Run KMeans clustering on the assembled dataset (features only)."""
    df = assemble_dataset(db)
    # Fill NaNs
    X = df.apply(lambda col: col.fillna(col.mean()))
    km = KMeans(n_clusters=k, random_state=random_state)
    labels = km.fit_predict(X)

    results = {
        "kmeans": {
            "k": int(k),
            "inertia": float(km.inertia_),
            "cluster_centers": km.cluster_centers_.tolist(),
        }
    }

    prefix = save_prefix or f"KM_{k}"
    dump(km, os.path.join(STORAGE_DIR, f"km_{prefix}.joblib"))
    pd.DataFrame(X, index=df.index).assign(cluster=labels).to_csv(
        os.path.join(STORAGE_DIR, f"km_assignments_{prefix}.csv")
    )
    with open(os.path.join(STORAGE_DIR, f"km_results_{prefix}.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    return {"labels": {int(i): int(l) for i, l in zip(df.index, labels)}, **results}


def _plot_feature_importances(importances: Dict[str, float], title: str, filename: str) -> None:
    """Plot feature importance as a sorted horizontal bar chart and save to file.

    - importances: mapping feature_name -> importance score
    - title: chart title
    - filename: output PNG path
    """
    if not importances:
        return
    # Sort descending
    items = sorted(importances.items(), key=lambda kv: kv[1], reverse=True)
    features = [k for k, _ in items]
    scores = [v for _, v in items]

    plt.figure(figsize=(10, max(4, len(features) * 0.4)))
    sns.set_style("whitegrid")
    sns.barplot(x=scores, y=features, orient="h", color="#0ea5e9")
    plt.xlabel("Importance Score")
    plt.ylabel("Features")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(filename, dpi=200, bbox_inches="tight")
    plt.close()


def generate_hotspot_map(
    db,
    target: str = "HPI",
    use_forecast: bool = False,
    horizon: int = 1,
    filename: Optional[str] = None,
    country: Optional[str] = None,
    heatmap: bool = True,
    center_lat: Optional[float] = None,
    center_lon: Optional[float] = None,
    radius_km: Optional[float] = None,
) -> Dict[str, Any]:
    """Generate an interactive Folium hotspot map for a target metric per sample.

    - target: index name like HPI/HEI/HI/Cd/CDI/MI or a metal symbol/name.
    - use_forecast: if True, uses forecasted next value; else uses current computed index.
    - horizon: forecast steps ahead (only when use_forecast=True).
    Returns dict with points and saved map path.
    """
    if folium is None:
        logger.warning("Hotspot: folium not installed; cannot generate interactive map HTML")
        return {"error": "folium not installed. Please add 'folium' to backend/requirements.txt and install.", "points": []}

    samples = db.query(Sample).all()
    logger.info("Hotspot: loaded %d samples", len(samples))
    points = []
    for s in samples:
        if s.latitude is None or s.longitude is None:
            logger.debug("Hotspot: skipping sample %s due to missing coordinates", getattr(s, 'id', '?'))
            continue
        # Metals and timeseries for this sample
        metals_rows = db.query(MetalConcentration).filter(MetalConcentration.sample_id == s.id).all()
        metals = {r.metal: float(r.value_mg_l) if r.value_mg_l is not None else np.nan for r in metals_rows}
        ts_rows = db.query(MetalTimeSeries).filter(MetalTimeSeries.sample_id == s.id).all()
        timeseries = {}
        for r in ts_rows:
            timeseries.setdefault(r.metal, {})[str(r.period)] = float(r.value_mg_l) if r.value_mg_l is not None else np.nan

        value = None
        if use_forecast and timeseries:
            try:
                fc = forecast_timeseries(db, sample_id=s.id, target=target, horizon=max(1, int(horizon)), model="auto")
                if not fc.get("error") and fc.get("forecast", {}).get("values"):
                    value = float(fc["forecast"]["values"][0]) if fc.get("forecast", {}).get("values") else None
                else:
                    logger.debug("Hotspot: forecast unavailable for sample %s target %s; error=%s", s.id, target, fc.get("error"))
            except Exception:
                logger.exception("Hotspot: forecast raised exception for sample %s target %s", s.id, target)
                value = None
        if value is None:
            # compute current index or metal value
            idx = _indices_for_sample(metals, timeseries if timeseries else None)
            key = target.upper()
            if key in idx:
                value = idx[key]
            elif target in metals:
                value = metals.get(target)
            else:
                # try lowercase metal name to symbol conversion by using indices table fallback
                value = None

        if value is None or not np.isfinite(value):
            logger.debug("Hotspot: skipping sample %s due to missing/invalid value for target %s", s.id, target)
            continue
        points.append({
            "sample_id": int(s.id),
            "lat": float(s.latitude),
            "lon": float(s.longitude),
            "value": float(value),
        })

    if not points:
        logger.warning("Hotspot: no points generated (target=%s, use_forecast=%s)", target, use_forecast)
        return {"error": "No points with coordinates and values found. Ensure samples have latitude/longitude and the selected target has values (for forecast, >=3 historical points).", "points": []}

    # Optional local region filtering by center/radius
    def _haversine_km(lat1, lon1, lat2, lon2):
        R = 6371.0
        p1 = np.radians([lat1, lon1])
        p2 = np.radians([lat2, lon2])
        dlat = p2[0] - p1[0]
        dlon = p2[1] - p1[1]
        a = np.sin(dlat/2)**2 + np.cos(p1[0]) * np.cos(p2[0]) * np.sin(dlon/2)**2
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
        return float(R * c)

    if center_lat is not None and center_lon is not None and radius_km is not None and radius_km > 0:
        before = len(points)
        points = [p for p in points if _haversine_km(center_lat, center_lon, p["lat"], p["lon"]) <= radius_km]
        logger.info("Hotspot: filtered points by radius %.1f km around (%.4f, %.4f): %d -> %d", radius_km, center_lat, center_lon, before, len(points))

    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    vals = [p["value"] for p in points]
    lat_c = float(np.mean(lats)) if lats else (center_lat if center_lat is not None else 0.0)
    lon_c = float(np.mean(lons)) if lons else (center_lon if center_lon is not None else 0.0)
    vmin, vmax = float(np.min(vals)), float(np.max(vals))
    # Avoid zero range
    rng = vmax - vmin if vmax > vmin else 1.0

    # Simple color scale green->red
    def color_for(v: float) -> str:
        t = (v - vmin) / rng
        # interpolate between green (0, 200, 80) and red (220, 50, 50)
        g0, r0, b0 = 200, 0, 80
        r1, g1, b1 = 220, 50, 50
        r = int(r0 + t * (r1 - r0))
        g = int(g0 + t * (g1 - g0))
        b = int(b0 + t * (b1 - b0))
        return f"#{r:02x}{g:02x}{b:02x}"

    # Create map; if India requested, center and bound to India
    if center_lat is not None and center_lon is not None and radius_km is not None and radius_km > 0 and points:
        # Compute a bounding box around center using rough degree approximation (good enough for small radii)
        # 1 deg lat ~ 111 km; 1 deg lon ~ 111 km * cos(lat)
        dlat = radius_km / 111.0
        dlon = radius_km / max(1e-6, (111.0 * np.cos(np.radians(center_lat))))
        sw = [center_lat - dlat, center_lon - dlon]
        ne = [center_lat + dlat, center_lon + dlon]
        m = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles="CartoDB positron")
        try:
            m.fit_bounds([sw, ne])
        except Exception:
            pass
    elif (country or '').lower() == 'india':
        m = folium.Map(location=[22.9734, 78.6569], zoom_start=5, tiles="CartoDB positron")
        # India approx bounds
        india_sw = [6.0, 68.0]
        india_ne = [37.5, 97.5]
        try:
            m.fit_bounds([india_sw, india_ne])
        except Exception:
            pass
    else:
        # Auto-fit to all points; for single point, use a close zoom
        if len(points) == 1:
            only = points[0]
            m = folium.Map(location=[only["lat"], only["lon"]], zoom_start=16, tiles="CartoDB positron")
        else:
            m = folium.Map(location=[lat_c, lon_c], zoom_start=8, tiles="CartoDB positron")
            try:
                lat_min, lat_max = min(lats), max(lats)
                lon_min, lon_max = min(lons), max(lons)
                # add small padding
                pad_lat = max(0.02, (lat_max - lat_min) * 0.1)
                pad_lon = max(0.02, (lon_max - lon_min) * 0.1)
                sw = [lat_min - pad_lat, lon_min - pad_lon]
                ne = [lat_max + pad_lat, lon_max + pad_lon]
                m.fit_bounds([sw, ne])
            except Exception:
                pass
    for p in points:
        radius = 6 + 14 * ((p["value"] - vmin) / rng)
        folium.CircleMarker(
            location=[p["lat"], p["lon"]],
            radius=float(radius),
            color=color_for(p["value"]),
            fill=True,
            fill_opacity=0.7,
            popup=f"Sample {p['sample_id']} | {target.upper()}={p['value']:.3f}",
        ).add_to(m)

    # Optional heatmap overlay
    if heatmap and folium_plugins is not None:
        try:
            hm_data = [[p['lat'], p['lon'], p['value']] for p in points]
            # Normalize intensities to [0,1]
            hm_norm = []
            for lat, lon, v in hm_data:
                t = (v - vmin) / rng if rng > 0 else 0.5
                hm_norm.append([lat, lon, max(0.0, min(1.0, float(t)))])
            folium_plugins.HeatMap(hm_norm, radius=18, blur=22, max_zoom=12, min_opacity=0.3).add_to(m)
        except Exception:
            logger.exception("Hotspot: failed to add HeatMap overlay")

    os.makedirs(STORAGE_DIR, exist_ok=True)
    mode = "forecast" if use_forecast else "current"
    out_path = filename or os.path.join(STORAGE_DIR, f"hotspot_{target.upper()}_{mode}.html")
    m.save(out_path)
    # Also render a static PNG map image using OSM tiles if available (staticmap)
    img_out_path = ""
    if StaticMap is not None and CircleMarker is not None:
        try:
            width, height = 800, 600
            m_img = StaticMap(width, height, url_template='https://a.tile.openstreetmap.org/{z}/{x}/{y}.png')
            # Color interpolation function
            def _col(v):
                t = (v - vmin) / (rng if rng > 0 else 1.0)
                r = int(255 * min(1.0, max(0.0, t)))
                g = int(200 * min(1.0, max(0.0, 1.0 - t)))
                b = 50
                return f"#{r:02x}{g:02x}{b:02x}"
            for p in points:
                color = _col(p['value'])
                m_img.add_marker(CircleMarker((p['lon'], p['lat']), color, 12))
            # Choose zoom: derive from radius if provided
            img = None
            if center_lat is not None and center_lon is not None and radius_km is not None and radius_km > 0:
                # Heuristic: zoom ~ 14 - log2(radius_km), clamp [4, 17]
                import math
                zoom = int(max(4, min(17, round(14 - math.log(max(1.0, radius_km), 2)))))
                img = m_img.render(zoom=zoom, center=(center_lon, center_lat))
            else:
                # Fit to markers
                img = m_img.render()
            img_out_path = os.path.join(STORAGE_DIR, f"hotspot_{target.upper()}_{mode}.png")
            img.save(img_out_path)
        except Exception:
            logger.exception("Hotspot: staticmap render failed, falling back to Matplotlib scatter")
            img_out_path = ""
    # Fallback: simple Matplotlib scatter without tiles
    if not img_out_path:
        try:
            fig_w, fig_h = 8, 6
            fig, ax = plt.subplots(figsize=(fig_w, fig_h))
            if center_lat is not None and center_lon is not None and radius_km is not None and radius_km > 0:
                dlat = radius_km / 111.0
                dlon = radius_km / max(1e-6, (111.0 * np.cos(np.radians(center_lat))))
                ax.set_xlim(center_lon - dlon, center_lon + dlon)
                ax.set_ylim(center_lat - dlat, center_lat + dlat)
            else:
                pad_lat = max(0.1, (max(lats) - min(lats)) * 0.2 if lats else 0.5)
                pad_lon = max(0.1, (max(lons) - min(lons)) * 0.2 if lons else 0.5)
                ax.set_xlim((min(lons) - pad_lon) if lons else -1, (max(lons) + pad_lon) if lons else 1)
                ax.set_ylim((min(lats) - pad_lat) if lats else -1, (max(lats) + pad_lat) if lats else 1)
            norm = (np.array(vals) - vmin) / (rng if rng > 0 else 1.0) if vals else np.array([])
            colors = [ (norm[i], max(0.2, 1.0 - norm[i]), 0.2) for i in range(len(points)) ] if len(points) else []
            ax.scatter([p['lon'] for p in points], [p['lat'] for p in points], c=colors, s=80, edgecolors='k', alpha=0.8)
            ax.set_xlabel('Longitude')
            ax.set_ylabel('Latitude')
            ax.set_title(f"{target.upper()} hotspot ({mode})")
            img_out_path = os.path.join(STORAGE_DIR, f"hotspot_{target.upper()}_{mode}.png")
            fig.tight_layout()
            fig.savefig(img_out_path, dpi=200)
            plt.close(fig)
        except Exception:
            logger.exception("Hotspot: failed to render Matplotlib scatter image")
            img_out_path = ""

    # Also compute static URLs (served by /static mount) for convenience
    map_url = f"/static/ml/{os.path.basename(out_path)}"
    image_url = f"/static/ml/{os.path.basename(img_out_path)}" if img_out_path else None

    return {"target": target.upper(), "mode": mode, "points": points, "map_path": out_path, "map_url": map_url, "image_path": img_out_path, "image_url": image_url}


# --------------------------- Time Series Forecasting ---------------------------

MONTH_ORDER = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def _order_period_keys(keys: List[str]) -> List[str]:
    # If all are month names, keep MONTH_ORDER subset; else sort
    if all(k in MONTH_ORDER for k in keys):
        return [m for m in MONTH_ORDER if m in keys]
    try:
        # Try to parse numeric or year-month strings
        def _key(v):
            # supports 'YYYY-MM' or integer-like
            try:
                if isinstance(v, (int, float)):
                    return float(v)
                s = str(v)
                if "-" in s:
                    parts = s.split("-")
                    return float(parts[0]) * 100 + float(parts[1])
                return float(s)
            except Exception:
                return float("inf")
        return sorted(keys, key=_key)
    except Exception:
        return sorted(keys)


def _target_series_from_timeseries(timeseries: Dict[str, Dict[str, float]], target: str) -> Dict[str, float]:
    target_u = target.upper()
    if target_u == "HPI":
        from .indices import compute_hpi_from_timeseries
        res = compute_hpi_from_timeseries(timeseries)
        return res.get("per_month", {})
    if target_u == "CD":
        from .indices import compute_cd_from_timeseries
        res = compute_cd_from_timeseries(timeseries)
        return res.get("per_month", {})
    if target_u == "HEI":
        from .indices import compute_hei_from_timeseries
        res = compute_hei_from_timeseries(timeseries)
        return res.get("per_month", {})
    if target_u in ("HI", "HQ"):
        from .indices import compute_hq_from_timeseries
        res = compute_hq_from_timeseries(timeseries)
        return res.get("per_month", {})
    # Fallback: if metal name provided as target, return that metal's series
    if target in timeseries:
        return timeseries.get(target, {})
    return {}


def _collect_sample_timeseries_union(db, sample_id: int) -> Dict[str, Dict[str, float]]:
    rows = db.query(MetalTimeSeries).filter(MetalTimeSeries.sample_id == sample_id).all()
    ts: Dict[str, Dict[str, float]] = {}
    for r in rows:
        ts.setdefault(r.metal, {})[str(r.period)] = float(r.value_mg_l) if r.value_mg_l is not None else np.nan
    return ts


def forecast_timeseries(
    db,
    sample_id: int,
    target: str = "HPI",
    horizon: int = 6,
    model: str = "auto",
    save_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """Forecast next `horizon` periods for a per-sample target index (e.g., HPI/HEI) or metal.

    Models: 'linear', 'poly2', 'gbr', or 'auto' (tries GBR then linear fallback).
    Returns dict with history, forecast, ci bands, and file path to chart.
    """
    ts = _collect_sample_timeseries_union(db, sample_id)
    if not ts:
        return {"error": "No time series data found for sample"}
    series = _target_series_from_timeseries(ts, target)
    if not series:
        return {"error": f"No series computed for target '{target}'"}

    periods = _order_period_keys(list(series.keys()))
    y_hist = []
    for p in periods:
        v = series.get(p, np.nan)
        try:
            y_hist.append(float(v))
        except Exception:
            y_hist.append(np.nan)
    # drop NaNs
    idx_valid = [i for i, v in enumerate(y_hist) if np.isfinite(v)]
    if len(idx_valid) < 3:
        return {"error": "Insufficient historical points for forecasting"}
    periods = [periods[i] for i in idx_valid]
    y_hist = [y_hist[i] for i in idx_valid]

    # X = 1..n
    n = len(y_hist)
    X = np.arange(1, n + 1).reshape(-1, 1)

    # choose model
    y_pred_hist = None
    forecaster = None
    used_model = model
    try:
        if model == "auto" or model == "gbr":
            gbr = GradientBoostingRegressor(random_state=42)
            gbr.fit(X, y_hist)
            y_pred_hist = gbr.predict(X)
            forecaster = gbr
            used_model = "gbr"
        elif model == "poly2":
            poly = PolynomialFeatures(degree=2, include_bias=False)
            Xp = poly.fit_transform(X)
            lr = LinearRegression()
            lr.fit(Xp, y_hist)
            y_pred_hist = lr.predict(Xp)
            forecaster = (lr, poly)
            used_model = "poly2"
        else:
            lr = LinearRegression()
            lr.fit(X, y_hist)
            y_pred_hist = lr.predict(X)
            forecaster = lr
            used_model = "linear"
    except Exception:
        # fallback to linear
        lr = LinearRegression()
        lr.fit(X, y_hist)
        y_pred_hist = lr.predict(X)
        forecaster = lr
        used_model = "linear"

    # residual std for CI
    resid = np.array(y_hist) - np.array(y_pred_hist)
    resid_std = float(np.std(resid, ddof=1)) if len(resid) > 1 else 0.0
    ci_k = 1.96

    # Forecast for next horizon
    Xf = np.arange(n + 1, n + horizon + 1).reshape(-1, 1)
    if used_model == "poly2":
        lr, poly = forecaster
        Xf_t = poly.transform(Xf)
        y_fc = lr.predict(Xf_t)
    else:
        y_fc = forecaster.predict(Xf)
    ci_low = (np.array(y_fc) - ci_k * resid_std).tolist()
    ci_high = (np.array(y_fc) + ci_k * resid_std).tolist()

    # Build future period labels continuation
    def next_labels(keys: List[str], h: int) -> List[str]:
        if all(k in MONTH_ORDER for k in keys):
            last_idx = MONTH_ORDER.index(keys[-1])
            out = []
            for i in range(1, h + 1):
                out.append(MONTH_ORDER[(last_idx + i) % 12])
            return out
        # numeric indexing
        base = len(keys)
        return [f"t+{i}" for i in range(1, h + 1)]

    future_labels = next_labels(periods, horizon)

    # Threshold flag (only for HPI by default)
    threshold = 100.0 if target.upper() == "HPI" else None
    flagged = []
    if threshold is not None:
        for i, v in enumerate(y_fc):
            if np.isfinite(v) and v > threshold:
                flagged.append(future_labels[i])

    # Plot
    os.makedirs(STORAGE_DIR, exist_ok=True)
    title = f"Forecast {target.upper()} for Sample {sample_id}"
    filename = os.path.join(STORAGE_DIR, f"forecast_{target.upper()}_S{sample_id}.png")
    try:
        plt.figure(figsize=(10, 5))
        # history
        plt.plot(range(1, n + 1), y_hist, label="History", color="#1f77b4")
        # fitted
        plt.plot(range(1, n + 1), y_pred_hist, label=f"Fitted ({used_model})", color="#2ca02c", linestyle="--")
        # forecast
        xf_axis = list(range(n + 1, n + horizon + 1))
        plt.plot(xf_axis, y_fc, label="Forecast", color="#d62728", linestyle=":")
        # CI
        plt.fill_between(xf_axis, ci_low, ci_high, color="#d62728", alpha=0.15, label="95% CI")
        # flags
        if flagged:
            for i, lab in enumerate(future_labels):
                if lab in flagged:
                    plt.scatter(xf_axis[i], y_fc[i], color="#B91C1C", zorder=3)
        plt.xlabel("Period")
        plt.ylabel(target.upper())
        plt.title(title)
        plt.legend()
        plt.tight_layout()
        plt.savefig(filename, dpi=200, bbox_inches="tight")
        plt.close()
    except Exception:
        # plotting failure should not break
        filename = ""

    return {
        "sample_id": int(sample_id),
        "target": target.upper(),
        "model": used_model,
        "history": {"periods": periods, "values": y_hist},
        "forecast": {"periods": future_labels, "values": [float(v) for v in y_fc]},
        "ci_low": [float(v) for v in ci_low],
        "ci_high": [float(v) for v in ci_high],
        "flagged": flagged,
        "plot_path": filename,
    }
