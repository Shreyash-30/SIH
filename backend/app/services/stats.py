import math
from typing import Dict, Optional, Union, Tuple, Any
import io
import base64

import numpy as np
import pandas as pd
from scipy import stats as spstats
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler


Number = Union[int, float, np.number]


def _coerce_series(values: Union[pd.Series, Dict[str, Number], list, np.ndarray]) -> pd.Series:
    if isinstance(values, pd.Series):
        return values.astype(float)
    if isinstance(values, dict):
        return pd.Series(values, dtype=float)
    return pd.Series(list(values), dtype=float)


def describe_series(values: Union[pd.Series, Dict[str, Number], list, np.ndarray]) -> Dict[str, Number]:
    """Return descriptive statistics for a 1D vector of concentrations.

    Includes: count, mean, median, mode (first), std, var, min, max, q1, q3,
    iqr, skewness, kurtosis (Fisher), geometric_mean, harmonic_mean (when valid).
    """
    s = _coerce_series(values).dropna()
    res: Dict[str, Number] = {}
    if s.empty:
        return {k: float('nan') for k in [
            'count','mean','median','mode','std','var','min','max','q1','q3','iqr','skew','kurtosis','geometric_mean','harmonic_mean'
        ]}

    desc = s.describe(percentiles=[0.25, 0.5, 0.75])
    res['count'] = float(desc['count'])
    res['mean'] = float(desc['mean'])
    res['median'] = float(desc['50%'])
    # Mode: use pandas mode; fallback to NaN
    try:
        mode_vals = s.mode(dropna=True)
        res['mode'] = float(mode_vals.iloc[0]) if not mode_vals.empty else float('nan')
    except Exception:
        res['mode'] = float('nan')
    res['std'] = float(s.std(ddof=1)) if s.size > 1 else float('nan')
    res['var'] = float(s.var(ddof=1)) if s.size > 1 else float('nan')
    res['min'] = float(desc['min'])
    res['max'] = float(desc['max'])
    res['q1'] = float(desc['25%'])
    res['q3'] = float(desc['75%'])
    res['iqr'] = float(res['q3'] - res['q1'])
    # Skewness & kurtosis
    try:
        res['skew'] = float(spstats.skew(s, bias=False, nan_policy='omit'))
        res['kurtosis'] = float(spstats.kurtosis(s, fisher=True, bias=False, nan_policy='omit'))
    except Exception:
        res['skew'] = float('nan')
        res['kurtosis'] = float('nan')
    # Geometric & harmonic means: only for positive values
    positives = s[s > 0]
    if positives.empty:
        res['geometric_mean'] = float('nan')
        res['harmonic_mean'] = float('nan')
    else:
        try:
            res['geometric_mean'] = float(spstats.gmean(positives))
        except Exception:
            res['geometric_mean'] = float('nan')
        try:
            res['harmonic_mean'] = float(spstats.hmean(positives))
        except Exception:
            res['harmonic_mean'] = float('nan')
    return res


def describe_dataframe(df: pd.DataFrame, axis: int = 0) -> Dict[str, Dict[str, Number]]:
    """Compute descriptive stats across rows (axis=1) or columns (axis=0)."""
    out: Dict[str, Dict[str, Number]] = {}
    if df is None or df.empty:
        return out
    if axis == 0:
        for col in df.columns:
            out[str(col)] = describe_series(df[col])
    else:
        for idx in df.index:
            out[str(idx)] = describe_series(df.loc[idx, :])
    return out


def describe_metals_dict(metals_mg_l: Dict[str, Number]) -> Dict[str, Number]:
    """Stats over a single-sample metals dict (mg/L by metal)."""
    return describe_series(pd.Series(metals_mg_l, dtype=float))


def describe_timeseries(timeseries: Dict[str, Dict[str, Number]], by: str = 'metal') -> Dict[str, Dict[str, Number]]:
    """Stats for timeseries shaped as metal -> period -> value (mg/L).

    by='metal': stats across periods for each metal.
    by='period': stats across metals for each period.
    """
    if not timeseries:
        return {}
    metals = list(timeseries.keys())
    periods = sorted({p for m in metals for p in timeseries[m].keys()})
    df = pd.DataFrame(index=metals, columns=periods, dtype=float)
    for m, ser in timeseries.items():
        for p, v in ser.items():
            try:
                df.loc[m, p] = float(v)
            except Exception:
                df.loc[m, p] = np.nan
    if by == 'period':
        return describe_dataframe(df.T, axis=0)
    return describe_dataframe(df, axis=1)


# --------------------------- Correlation Analysis ---------------------------

def compute_correlation_matrix(
    data: Union[pd.DataFrame, Dict[str, Dict[str, Number]]], 
    method: str = 'pearson'
) -> pd.DataFrame:
    """Compute correlation matrix for metals and pollution indices.
    
    Args:
        data: DataFrame or timeseries dict (metal->period->value)
        method: 'pearson' or 'spearman'
    
    Returns:
        Correlation matrix as DataFrame
    """
    if isinstance(data, dict):
        # Convert timeseries to DataFrame
        metals = list(data.keys())
        periods = sorted({p for m in metals for p in data[m].keys()})
        df = pd.DataFrame(index=metals, columns=periods, dtype=float)
        for m, ser in data.items():
            for p, v in ser.items():
                try:
                    df.loc[m, p] = float(v)
                except Exception:
                    df.loc[m, p] = np.nan
        data = df
    
    if method.lower() == 'pearson':
        return data.corr(method='pearson')
    elif method.lower() == 'spearman':
        return data.corr(method='spearman')
    else:
        raise ValueError("Method must be 'pearson' or 'spearman'")


def compute_metals_indices_correlation(
    timeseries: Dict[str, Dict[str, Number]],
    method: str = 'pearson',
    preprocess: bool = False,
    cleaning_kwargs: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Compute correlations between metals and pollution indices (HPI, Cd, HEI, HI).
    
    Args:
        timeseries: metal->period->value (mg/L)
        method: 'pearson' or 'spearman'
    
    Returns:
        Dict with correlation matrices and summary stats
    """
    if not timeseries:
        return {}
    
    # Import indices functions
    from .indices import (
        compute_hpi_from_timeseries, 
        compute_cd_from_timeseries,
        compute_hei_from_timeseries,
        compute_hq_from_timeseries
    )
    
    # Optional preprocessing
    if preprocess:
        from .cleaning import preprocess_timeseries
        timeseries = preprocess_timeseries(timeseries, **(cleaning_kwargs or {}))

    # Compute pollution indices
    hpi_results = compute_hpi_from_timeseries(timeseries)
    cd_results = compute_cd_from_timeseries(timeseries)
    hei_results = compute_hei_from_timeseries(timeseries)
    hi_results = compute_hq_from_timeseries(timeseries)
    
    # Extract per-month values
    periods = set()
    for results in [hpi_results, cd_results, hei_results, hi_results]:
        if 'per_month' in results:
            periods.update(results['per_month'].keys())
    
    if not periods:
        return {}
    
    # Build DataFrame with metals and indices
    metals = list(timeseries.keys())
    periods = sorted(periods)
    
    # Create DataFrame: rows=periods, columns=metals+indices
    df = pd.DataFrame(index=periods)
    
    # Add metal concentrations
    for metal in metals:
        df[metal] = [timeseries[metal].get(p, np.nan) for p in periods]
    
    # Add pollution indices
    df['HPI'] = [hpi_results.get('per_month', {}).get(p, np.nan) for p in periods]
    df['Cd'] = [cd_results.get('per_month', {}).get(p, np.nan) for p in periods]
    df['HEI'] = [hei_results.get('per_month', {}).get(p, np.nan) for p in periods]
    df['HI'] = [hi_results.get('per_month', {}).get(p, np.nan) for p in periods]
    
    # Compute correlation matrix
    corr_matrix = compute_correlation_matrix(df, method=method)
    
    # Extract metal-indices correlations
    metals_cols = [col for col in df.columns if col in metals]
    indices_cols = ['HPI', 'Cd', 'HEI', 'HI']
    
    metal_index_corr = corr_matrix.loc[metals_cols, indices_cols]
    
    return {
        'full_correlation_matrix': corr_matrix.to_dict(),
        'metal_index_correlations': metal_index_corr.to_dict(),
        'method': method,
        'summary': {
            'n_periods': len(periods),
            'n_metals': len(metals),
            'n_indices': len(indices_cols)
        }
    }


def plot_correlation_heatmap(
    corr_matrix: pd.DataFrame,
    title: str = "Correlation Matrix",
    figsize: Tuple[int, int] = (10, 8),
    save_path: Optional[str] = None
) -> str:
    """Create and save correlation heatmap visualization.
    
    Args:
        corr_matrix: Correlation matrix DataFrame
        title: Plot title
        figsize: Figure size (width, height)
        save_path: Optional path to save image
    
    Returns:
        Base64 encoded image string if save_path is None, else file path
    """
    plt.figure(figsize=figsize)
    
    # Create heatmap
    mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
    sns.heatmap(
        corr_matrix,
        mask=mask,
        annot=True,
        cmap='RdBu_r',
        center=0,
        square=True,
        fmt='.3f',
        cbar_kws={"shrink": .8}
    )
    
    plt.title(title, fontsize=16, pad=20)
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        return save_path
    else:
        # Return as base64 string
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        return image_base64


def plot_metal_index_correlations(
    timeseries: Dict[str, Dict[str, Number]],
    method: str = 'pearson',
    preprocess: bool = False,
    cleaning_kwargs: Optional[Dict] = None,
    figsize: Tuple[int, int] = (12, 8),
    save_path: Optional[str] = None
) -> str:
    """Create correlation plot between metals and pollution indices.
    
    Args:
        timeseries: metal->period->value (mg/L)
        method: 'pearson' or 'spearman'
        figsize: Figure size
        save_path: Optional path to save image
    
    Returns:
        Base64 encoded image string or file path
    """
    corr_data = compute_metals_indices_correlation(timeseries, method, preprocess=preprocess, cleaning_kwargs=cleaning_kwargs)
    
    if not corr_data or 'metal_index_correlations' not in corr_data:
        return ""
    
    metal_index_corr = pd.DataFrame(corr_data['metal_index_correlations'])
    
    plt.figure(figsize=figsize)
    
    # Create heatmap
    sns.heatmap(
        metal_index_corr,
        annot=True,
        cmap='RdBu_r',
        center=0,
        square=True,
        fmt='.3f',
        cbar_kws={"shrink": .8}
    )
    
    plt.title(f'Metal-Index Correlations ({method.title()})', fontsize=16, pad=20)
    plt.xlabel('Pollution Indices', fontsize=12)
    plt.ylabel('Metals', fontsize=12)
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        return save_path
    else:
        # Return as base64 string
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        return image_base64


def plot_correlation_scatter(
    timeseries: Dict[str, Dict[str, Number]],
    metal: str,
    index: str,
    method: str = 'pearson',
    preprocess: bool = False,
    cleaning_kwargs: Optional[Dict] = None,
    figsize: Tuple[int, int] = (8, 6),
    save_path: Optional[str] = None
) -> str:
    """Create scatter plot showing correlation between a specific metal and index.
    
    Args:
        timeseries: metal->period->value (mg/L)
        metal: Metal name to plot
        index: Index name ('HPI', 'Cd', 'HEI', 'HI')
        method: 'pearson' or 'spearman'
        figsize: Figure size
        save_path: Optional path to save image
    
    Returns:
        Base64 encoded image string or file path
    """
    if metal not in timeseries or index not in ['HPI', 'Cd', 'HEI', 'HI']:
        return ""
    
    # Import indices functions
    from .indices import (
        compute_hpi_from_timeseries, 
        compute_cd_from_timeseries,
        compute_hei_from_timeseries,
        compute_hq_from_timeseries
    )
    
    # Optional preprocessing
    ts = timeseries
    if preprocess:
        from .cleaning import preprocess_timeseries
        ts = preprocess_timeseries(timeseries, **(cleaning_kwargs or {}))

    # Get index values
    if index == 'HPI':
        index_results = compute_hpi_from_timeseries(ts)
    elif index == 'Cd':
        index_results = compute_cd_from_timeseries(ts)
    elif index == 'HEI':
        index_results = compute_hei_from_timeseries(ts)
    elif index == 'HI':
        index_results = compute_hq_from_timeseries(ts)
    
    # Align data
    periods = sorted(set(ts.get(metal, {}).keys()) & set(index_results.get('per_month', {}).keys()))
    
    if len(periods) < 2:
        return ""
    
    metal_values = [ts[metal][p] for p in periods]
    index_values = [index_results['per_month'][p] for p in periods]
    
    # Calculate correlation
    corr_coef, p_value = spstats.pearsonr(metal_values, index_values) if method == 'pearson' else spstats.spearmanr(metal_values, index_values)
    
    plt.figure(figsize=figsize)
    plt.scatter(metal_values, index_values, alpha=0.7, s=50)
    
    # Add trend line
    z = np.polyfit(metal_values, index_values, 1)
    p = np.poly1d(z)
    plt.plot(metal_values, p(metal_values), "r--", alpha=0.8)
    
    plt.xlabel(f'{metal} Concentration (mg/L)', fontsize=12)
    plt.ylabel(f'{index} Index', fontsize=12)
    plt.title(f'{metal} vs {index} ({method.title()}: r={corr_coef:.3f}, p={p_value:.3f})', fontsize=14)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        return save_path
    else:
        # Return as base64 string
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        return image_base64


# --------------------------- PCA (Principal Component Analysis) ---------------------------

def perform_pca_on_timeseries(
    timeseries: Dict[str, Dict[str, Number]],
    n_components: Optional[int] = None,
    scale: bool = True,
    preprocess: bool = False,
    cleaning_kwargs: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Run PCA on concentrations (metals x periods).

    Returns: dict containing components, explained_variance_ratio, scores per period, loadings per metal.
    """
    if not timeseries:
        return {}
    metals = list(timeseries.keys())
    periods = sorted({p for m in metals for p in timeseries[m].keys()})
    df = pd.DataFrame(index=metals, columns=periods, dtype=float)
    for m, ser in timeseries.items():
        for p, v in ser.items():
            try:
                df.loc[m, p] = float(v)
            except Exception:
                df.loc[m, p] = np.nan

    if preprocess:
        from .cleaning import preprocess_dataframe
        df = preprocess_dataframe(df, **(cleaning_kwargs or {}))

    if df.empty:
        return {}

    # Transpose: samples=periods, features=metals
    X = df.T.values
    # Handle any remaining NaNs by column mean (last resort)
    col_means = np.nanmean(X, axis=0)
    inds = np.where(np.isnan(X))
    X[inds] = np.take(col_means, inds[1])

    if scale:
        scaler = StandardScaler()
        X = scaler.fit_transform(X)

    pca = PCA(n_components=n_components)
    scores = pca.fit_transform(X)  # shape: n_periods x n_components
    loadings = pca.components_.T   # shape: n_metals x n_components

    result = {
        'periods': periods,
        'metals': df.index.tolist(),
        'components': int(pca.n_components_),
        'explained_variance_ratio': pca.explained_variance_ratio_.tolist(),
        'scores': pd.DataFrame(scores, index=periods).to_dict(orient='list'),
        'loadings': pd.DataFrame(loadings, index=df.index).to_dict(orient='list'),
    }
    return result


def plot_pca_scree(
    pca_result: Dict[str, Any],
    figsize: Tuple[int, int] = (8, 5),
    save_path: Optional[str] = None
) -> str:
    """Plot scree (explained variance by component)."""
    evr = pca_result.get('explained_variance_ratio', [])
    if not evr:
        return ""
    comps = np.arange(1, len(evr) + 1)
    plt.figure(figsize=figsize)
    plt.plot(comps, evr, 'o-', label='Explained variance ratio')
    plt.bar(comps, evr, alpha=0.3)
    plt.xlabel('Principal Component')
    plt.ylabel('Explained Variance Ratio')
    plt.title('PCA Scree Plot')
    plt.xticks(comps)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        return save_path
    else:
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        return image_base64


def plot_pca_biplot(
    pca_result: Dict[str, Any],
    comp_x: int = 1,
    comp_y: int = 2,
    figsize: Tuple[int, int] = (9, 7),
    save_path: Optional[str] = None
) -> str:
    """Create a PCA biplot for two components (scores + loadings)."""
    evr = pca_result.get('explained_variance_ratio', [])
    scores = pca_result.get('scores')
    loadings = pca_result.get('loadings')
    periods = pca_result.get('periods', [])
    metals = pca_result.get('metals', [])
    if not evr or scores is None or loadings is None:
        return ""

    # Convert dicts back to DataFrames for ease
    scores_df = pd.DataFrame(scores, index=periods)
    loadings_df = pd.DataFrame(loadings, index=metals)

    # component indices (0-based)
    cx = comp_x - 1
    cy = comp_y - 1
    if cx not in scores_df.columns or cy not in scores_df.columns:
        return ""

    plt.figure(figsize=figsize)
    # Scores scatter
    plt.scatter(scores_df[cx], scores_df[cy], alpha=0.7)
    for i, label in enumerate(periods):
        plt.annotate(str(label), (scores_df[cx].iloc[i], scores_df[cy].iloc[i]), fontsize=8, alpha=0.7)

    # Loadings arrows
    for i, metal in enumerate(metals):
        lx = loadings_df[cx].iloc[i]
        ly = loadings_df[cy].iloc[i]
        plt.arrow(0, 0, lx, ly, color='r', alpha=0.6, head_width=0.02, length_includes_head=True)
        plt.text(lx * 1.05, ly * 1.05, metal, color='r', ha='center', va='center', fontsize=9)

    plt.axhline(0, color='grey', linewidth=1)
    plt.axvline(0, color='grey', linewidth=1)
    plt.xlabel(f'PC{comp_x} ({evr[cx]*100:.1f}%)')
    plt.ylabel(f'PC{comp_y} ({evr[cy]*100:.1f}%)')
    plt.title('PCA Biplot')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        return save_path
    else:
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        return image_base64


# --------------------------- Monthly Statistical Analysis ---------------------------

def compute_monthly_statistics(timeseries: Dict[str, Dict[str, Number]]) -> Dict[str, Dict[str, Number]]:
    """Compute descriptive statistics for each metal across all months.
    
    Args:
        timeseries: metal->period->value (mg/L) dictionary
        
    Returns:
        Dictionary with statistical measures for each metal
    """
    if not timeseries:
        return {}
    
    result = {}
    
    for metal, period_data in timeseries.items():
        if not period_data:
            continue
            
        # Convert to pandas Series for easier statistical computation
        values = pd.Series(list(period_data.values()), dtype=float)
        values = values.dropna()
        
        if len(values) == 0:
            continue
            
        # Calculate all statistical measures
        stats = describe_series(values)
        
        # Add additional measures
        stats['standard_error'] = float(values.sem()) if len(values) > 1 else 0.0
        stats['range'] = float(values.max() - values.min())
        stats['coefficient_of_variation'] = float(values.std() / values.mean()) if values.mean() != 0 else 0.0
        
        result[metal] = stats
    
    return result


def format_monthly_statistics_table(monthly_stats: Dict[str, Dict[str, Number]]) -> Dict[str, Any]:
    """Format monthly statistics into a table structure for frontend display.
    
    Args:
        monthly_stats: Output from compute_monthly_statistics()
        
    Returns:
        Formatted table data with statistical variables as rows and metals as columns
    """
    if not monthly_stats:
        return {"error": "No statistical data available"}
    
    # Define the statistical variables we want to display
    stat_variables = [
        'standard_error',
        'mean', 
        'median',
        'std',
        'var',
        'kurtosis',
        'skew',
        'range',
        'min',
        'max'
    ]
    
    # Create the table structure
    table_data = {}
    
    for stat_var in stat_variables:
        table_data[stat_var] = {}
        for metal, stats in monthly_stats.items():
            value = stats.get(stat_var, 0.0)
            # Round to appropriate decimal places
            if stat_var in ['standard_error', 'mean', 'median', 'std', 'min', 'max']:
                table_data[stat_var][metal] = round(float(value), 3)
            elif stat_var == 'var':
                table_data[stat_var][metal] = round(float(value), 6)
            else:  # kurtosis, skew
                table_data[stat_var][metal] = round(float(value), 3)
    
    return {
        "statistical_variables": stat_variables,
        "metals": list(monthly_stats.keys()),
        "table_data": table_data,
        "title": "Monthly Statistical Analysis of Metal Concentrations"
    }


# --------------------------- Mean vs Limit Bar Plot ---------------------------
def plot_mean_vs_limit_bar(
    series: Dict[str, Tuple[float, float]],
    title: str,
    out_path: str,
    figsize: Tuple[int, int] = (10, 4),
) -> str:
    """Render a bar chart of mean vs permissible limit per metal and save PNG.

    Args:
        series: mapping metal -> (mean_mgL, limit_mgL)
        title: chart title
        out_path: file path to save PNG
        figsize: figure size

    Returns:
        out_path on success (empty string if no data)
    """
    if not series:
        return ""

    metals = list(series.keys())
    means = [float(series[m][0]) if series[m][0] is not None else np.nan for m in metals]
    limits = [float(series[m][1]) if series[m][1] is not None else np.nan for m in metals]

    x = np.arange(len(metals))
    bar_w = 0.6

    plt.figure(figsize=figsize)
    ax = plt.gca()

    # Colors green below/equal limit, red if exceed; gray if mean missing
    colors = []
    for mean, lim in zip(means, limits):
        if np.isnan(mean):
            colors.append('#9CA3AF')  # gray for missing
        elif np.isnan(lim) or mean <= lim:
            colors.append('#10b981')  # green
        else:
            colors.append('#ef4444')  # red

    ax.bar(x, [0 if np.isnan(v) else v for v in means], width=bar_w, color=colors, edgecolor='#374151')

    # Draw per-metal limit dashed lines centered on each bar
    for xi, lim in zip(x, limits):
        if np.isnan(lim) or lim < 0:
            continue
        ax.hlines(lim, xi - bar_w/2 - 0.05, xi + bar_w/2 + 0.05, colors='#111827', linestyles='dashed', linewidth=1.5)

    ax.set_xticks(x)
    ax.set_xticklabels(metals, rotation=45, ha='right')
    ax.set_ylabel('Concentration (mg/L)')
    ax.set_title(title)
    ax.grid(axis='y', alpha=0.2)
    plt.tight_layout()
    plt.savefig(out_path, dpi=180, bbox_inches='tight')
    plt.close()
    return out_path
