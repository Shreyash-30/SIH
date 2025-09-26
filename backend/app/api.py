import os
import uuid
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from pydantic import BaseModel
from .database import get_db, Base, engine
from .services.extract import extract_file_data, detect_file_kind
from .models import Sample, MetalConcentration, MetalTimeSeries, MetalSampleSeries
from sqlalchemy.orm import Session
from .services.limits import get_limit_mg_l, get_weight, get_standard_id, _active_limits_mg_l
from .services.indices import compute_monthly_mi_from_timeseries, format_metal_indices_table, format_metal_formula_table
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

router = APIRouter()

ACCEPTED_MIME = {
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/pdf",
}
MAX_SIZE = 50 * 1024 * 1024
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./backend/storage/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

class UploadResponse(BaseModel):
    id: int
    file_path: str
    summary: Dict[str, int]
    extracted_metals: Optional[Dict[str, float]] = None
    timeseries: Optional[Dict[str, Dict[str, float]]] = None
    limits_mg_l: Optional[Dict[str, float]] = None
    assessments: Optional[Dict[str, Dict[str, Optional[float]]]] = None
    indices: Optional[Dict[str, Any]] = None
    metadata_json: Optional[str] = None

class SampleListItem(BaseModel):
    id: int
    sample_id: Optional[str]
    lab_name: Optional[str]
    collection_date: Optional[str]
    metals_count: int

class SampleDetail(BaseModel):
    id: int
    sample_id: Optional[str]
    lab_name: Optional[str]
    collection_date: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    metadata_json: Optional[str]
    file_path: str
    metals: Dict[str, float]
    timeseries: Optional[Dict[str, Dict[str, float]]] = None
    limits_mg_l: Optional[Dict[str, float]] = None
    assessments: Optional[Dict[str, Dict[str, Optional[float]]]] = None
    indices: Optional[Dict[str, Any]] = None

@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if file.content_type not in ACCEPTED_MIME:
        raise HTTPException(status_code=400, detail="Unsupported format. Use CSV, Excel, or PDF.")

    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Max 50MB.")

    ext = os.path.splitext(file.filename)[1]
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(dest_path, "wb") as f:
        f.write(contents)

    kind = detect_file_kind(file.filename, file.content_type)
    extracted = extract_file_data(dest_path, kind)

    sample = Sample(
        sample_id=extracted.sample_id,
        collection_date=extracted.collection_date,
        lab_name=extracted.lab_name,
        latitude=extracted.latitude,
        longitude=extracted.longitude,
        metadata_json=extracted.metadata,
        file_path=dest_path,
    )
    db.add(sample)
    db.flush()

    metals_count = 0
    assessments: Dict[str, Dict[str, float]] = {}
    exceed_count = 0
    severe_exceed = False
    strict_factor = float(os.getenv("STRICT_UNSAFE_FACTOR", 2))
    for metal, value in (extracted.metals or {}).items():
        mc = MetalConcentration(sample_id=sample.id, metal=metal, value_mg_l=value)
        db.add(mc)
        metals_count += 1
        limit = get_limit_mg_l(metal)
        exceeds = 1.0 if (limit is not None and value is not None and value > limit) else 0.0
        if exceeds:
            exceed_count += 1
            if limit is not None and value is not None and value >= strict_factor * limit:
                severe_exceed = True
        weight = get_weight(metal)
        assessments[metal] = {
            "value_mg_l": value if value is not None else None,
            "limit_mg_l": limit if limit is not None else None,
            "exceeds": float(exceeds),
            "weight": weight if weight is not None else None,
        }

    # Store time series if present
    if getattr(extracted, 'timeseries', None):
        for metal, series in (extracted.timeseries or {}).items():
            for period, val in series.items():
                db.add(MetalTimeSeries(sample_id=sample.id, metal=metal, period=str(period), value_mg_l=val))

    # Store sample series if present
    if getattr(extracted, 'sample_series', None):
        for metal, series in (extracted.sample_series or {}).items():
            for label, val in series.items():
                db.add(MetalSampleSeries(sample_id=sample.id, metal=metal, sample_label=str(label), value_mg_l=val))

    db.commit()
    # Compute and store monthly MI if we have month-wise timeseries
    indices = None
    if getattr(extracted, 'timeseries', None):
        mi = compute_monthly_mi_from_timeseries(extracted.timeseries or {})
        if mi:
            from .models import ComputedIndex
            db.add(ComputedIndex(sample_id=sample.id, kind="MI_monthly", data_json=json.dumps(mi)))
            db.commit()
    # Limits for metals present (from active standards)
    present_metals = set((extracted.metals or {}).keys())
    if getattr(extracted, 'timeseries', None):
        for m in extracted.timeseries.keys():
            present_metals.add(m)
    all_limits = _active_limits_mg_l()
    limits_subset = {m: all_limits.get(m) for m in present_metals if all_limits.get(m) is not None}

    return UploadResponse(
        id=sample.id,
        file_path=dest_path,
        summary={"metals": metals_count},
        extracted_metals=extracted.metals or {},
        timeseries=getattr(extracted, 'timeseries', None) or None,
        limits_mg_l=limits_subset or None,
        assessments=assessments or {},
        indices=indices,
        metadata_json=sample.metadata_json,
    )

@router.get("/samples", response_model=List[SampleListItem])
def list_samples(db: Session = Depends(get_db)):
    rows = db.query(Sample).all()
    result: List[SampleListItem] = []
    for s in rows:
        metals_count = db.query(MetalConcentration).filter(MetalConcentration.sample_id == s.id).count()
        result.append(
            SampleListItem(
                id=s.id,
                sample_id=s.sample_id,
                lab_name=s.lab_name,
                collection_date=s.collection_date,
                metals_count=metals_count,
            )
        )
    return result

@router.get("/samples/{sample_id}", response_model=SampleDetail)
def get_sample(sample_id: int, db: Session = Depends(get_db)):
    s = db.query(Sample).filter(Sample.id == sample_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Sample not found")
    metals_rows = db.query(MetalConcentration).filter(MetalConcentration.sample_id == s.id).all()
    metals: Dict[str, float] = {m.metal: m.value_mg_l for m in metals_rows}
    assessments: Dict[str, Dict[str, float]] = {}
    exceed_count = 0
    severe_exceed = False
    strict_factor = float(os.getenv("STRICT_UNSAFE_FACTOR", 2))
    for metal, value in metals.items():
        limit = get_limit_mg_l(metal)
        exceeds = 1.0 if (limit is not None and value is not None and value > limit) else 0.0
        if exceeds:
            exceed_count += 1
            if limit is not None and value is not None and value >= strict_factor * limit:
                severe_exceed = True
        weight = get_weight(metal)
        assessments[metal] = {
            "value_mg_l": value if value is not None else None,
            "limit_mg_l": limit if limit is not None else None,
            "exceeds": float(exceeds),
            "weight": weight if weight is not None else None,
        }
    # Build timeseries dict if rows present
    ts_rows = db.query(MetalTimeSeries).filter(MetalTimeSeries.sample_id == s.id).all()
    timeseries: Optional[Dict[str, Dict[str, float]]] = None
    if ts_rows:
        tmp: Dict[str, Dict[str, float]] = {}
        for r in ts_rows:
            tmp.setdefault(r.metal, {})[str(r.period)] = float(r.value_mg_l) if r.value_mg_l is not None else None
        timeseries = tmp

    # Compute pollution indices if metals are present
    indices = None
    if metals:
        from .services.indices import compute_hpi_from_metals
        try:
            hpi_result = compute_hpi_from_metals(metals)
            indices = {
                'hpi': hpi_result.get('hpi'),
                'exceed_count': exceed_count,
                'severe_exceed': severe_exceed
            }
        except Exception:
            indices = None
    return SampleDetail(
        id=s.id,
        sample_id=s.sample_id,
        lab_name=s.lab_name,
        collection_date=s.collection_date,
        latitude=s.latitude,
        longitude=s.longitude,
        metadata_json=s.metadata_json,
        file_path=s.file_path,
        metals=metals,
        timeseries=timeseries,
        limits_mg_l={k: v for k, v in _active_limits_mg_l().items() if k in metals or (timeseries and k in timeseries)},
        assessments=assessments or None,
        indices=indices,
    )

# Statistical Analysis Endpoints

@router.get("/stats/summary")
def get_descriptive_stats(db: Session = Depends(get_db)):
    """Get descriptive statistics for all metals across all samples"""
    # Get all metal concentrations
    metals_data = db.query(MetalConcentration).all()
    if not metals_data:
        return {"error": "No metal concentration data found"}
    
    # Convert to DataFrame
    df = pd.DataFrame([{
        'metal': m.metal,
        'value': m.value_mg_l,
        'sample_id': m.sample_id
    } for m in metals_data])
    
    # Get sample metadata for additional parameters
    samples_data = db.query(Sample).all()
    samples_df = pd.DataFrame([{
        'sample_id': s.id,
        'ph': s.metadata_json.get('ph') if s.metadata_json else None,
        'tds': s.metadata_json.get('tds') if s.metadata_json else None,
        'ec': s.metadata_json.get('ec') if s.metadata_json else None,
        'collection_date': s.collection_date
    } for s in samples_data])
    
    # Merge data
    df = df.merge(samples_df, on='sample_id', how='left')
    
    # Calculate descriptive statistics for each metal
    metals = df['metal'].unique()
    stats = {}
    
    for metal in metals:
        metal_data = df[df['metal'] == metal]['value'].dropna()
        if len(metal_data) == 0:
            continue
            
        # Basic stats
        stats[metal] = {
            'count': len(metal_data),
            'mean': float(metal_data.mean()),
            'median': float(metal_data.median()),
            'std': float(metal_data.std()),
            'min': float(metal_data.min()),
            'max': float(metal_data.max()),
            'variance': float(metal_data.var()),
            'exceed_percentage': 0.0
        }
        
        # Calculate exceedance percentage
        limit = get_limit_mg_l(metal)
        if limit is not None:
            exceeds = metal_data > limit
            stats[metal]['exceed_percentage'] = float(exceeds.sum() / len(metal_data) * 100)
        
        # Outlier detection using IQR
        Q1 = metal_data.quantile(0.25)
        Q3 = metal_data.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        outliers = metal_data[(metal_data < lower_bound) | (metal_data > upper_bound)]
        stats[metal]['outliers_count'] = len(outliers)
        
        # Histogram data (10 bins)
        hist, bin_edges = np.histogram(metal_data, bins=10)
        stats[metal]['histogram'] = {
            'counts': hist.tolist(),
            'bin_edges': bin_edges.tolist()
        }
        
        # Box plot data
        stats[metal]['box_plot'] = {
            'q1': float(Q1),
            'q3': float(Q3),
            'median': float(metal_data.median()),
            'whisker_low': float(max(metal_data.min(), lower_bound)),
            'whisker_high': float(min(metal_data.max(), upper_bound)),
            'outliers': outliers.tolist()
        }
    
    return stats

@router.get("/stats/correlation")
def get_correlation_matrix(method: str = Query("pearson", regex="^(pearson|spearman)$"), db: Session = Depends(get_db)):
    """Get correlation matrix for metals and water quality parameters"""
    # Get all metal concentrations
    metals_data = db.query(MetalConcentration).all()
    if not metals_data:
        return {"error": "No metal concentration data found"}
    
    # Convert to wide format
    df = pd.DataFrame([{
        'sample_id': m.sample_id,
        'metal': m.metal,
        'value': m.value_mg_l
    } for m in metals_data])
    
    # Pivot to wide format
    metals_wide = df.pivot(index='sample_id', columns='metal', values='value')
    
    # Get sample metadata
    samples_data = db.query(Sample).all()
    for s in samples_data:
        if s.metadata_json:
            if 'ph' in s.metadata_json:
                metals_wide.loc[s.id, 'pH'] = s.metadata_json['ph']
            if 'tds' in s.metadata_json:
                metals_wide.loc[s.id, 'TDS'] = s.metadata_json['tds']
            if 'ec' in s.metadata_json:
                metals_wide.loc[s.id, 'EC'] = s.metadata_json['ec']
    
    # Calculate correlation matrix
    corr_matrix = metals_wide.corr(method=method)
    
    # Convert to dict format
    correlation_data = {
        'method': method,
        'matrix': corr_matrix.fillna(0).to_dict(),
        'metals': corr_matrix.columns.tolist()
    }
    
    return correlation_data

@router.get("/stats/trends")
def get_trend_analysis(db: Session = Depends(get_db)):
    """Get trend analysis for metals over discrete periods (month names) when no dates exist"""
    # Prefer dedicated time series table if present
    ts_rows = db.query(MetalTimeSeries).all()
    if ts_rows:
        trends: Dict[str, Dict[str, List]] = {}
        tmp: Dict[str, Dict[str, float]] = {}
        for r in ts_rows:
            tmp.setdefault(r.metal, {})[r.period] = r.value_mg_l
        for metal, ser in tmp.items():
            # order by fixed month order if month names, else sort by key
            order = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
            keys = list(ser.keys())
            if all(k in order for k in keys):
                keys = [m for m in order if m in ser]
            else:
                keys = sorted(keys)
            trends[metal] = {
                'dates': keys,
                'values': [ser[k] for k in keys],
            }
        return {'metals': trends}

    # Fallback: aggregate by collection_date if exists
    metals_data = db.query(MetalConcentration).join(Sample).all()
    df = pd.DataFrame([
        {'metal': m.metal, 'value': m.value_mg_l, 'date': m.sample.collection_date}
        for m in metals_data if m.sample and m.sample.collection_date
    ])
    if df.empty:
        return {'metals': {}}
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    trends = {}
    for metal in df['metal'].unique():
        metal_data = df[df['metal'] == metal]
        daily_avg = metal_data.groupby('date')['value'].mean().reset_index()
        trends[metal] = {
            'dates': daily_avg['date'].dt.strftime('%Y-%m-%d').tolist(),
            'values': daily_avg['value'].tolist()
        }
    return {'metals': trends}

@router.get("/stats/geo")
def get_geo_analysis(grid_size: int = Query(1000, description="Grid size in meters"), db: Session = Depends(get_db)):
    """Get geographical analysis and heatmap data"""
    # Get all samples with coordinates
    samples = db.query(Sample).filter(
        Sample.latitude.isnot(None),
        Sample.longitude.isnot(None)
    ).all()
    
    if not samples:
        return {"error": "No samples with coordinates found"}
    
    # Get metal concentrations for these samples
    sample_ids = [s.id for s in samples]
    metals_data = db.query(MetalConcentration).filter(
        MetalConcentration.sample_id.in_(sample_ids)
    ).all()
    
    # Convert to DataFrame
    df = pd.DataFrame([{
        'sample_id': m.sample_id,
        'metal': m.metal,
        'value': m.value_mg_l,
        'latitude': next(s.latitude for s in samples if s.id == m.sample_id),
        'longitude': next(s.longitude for s in samples if s.id == m.sample_id)
    } for m in metals_data])
    
    # Create grid-based aggregation
    df['lat_grid'] = (df['latitude'] * 1000 // grid_size * grid_size / 1000).round(3)
    df['lon_grid'] = (df['longitude'] * 1000 // grid_size * grid_size / 1000).round(3)
    
    geo_data = {
        'points': [],
        'grid': {}
    }
    
    # Individual points
    for metal in df['metal'].unique():
        metal_points = df[df['metal'] == metal]
        geo_data['points'].append({
            'metal': metal,
            'coordinates': metal_points[['latitude', 'longitude', 'value']].to_dict('records')
        })
    
    # Grid aggregation
    for metal in df['metal'].unique():
        metal_data = df[df['metal'] == metal]
        grid_avg = metal_data.groupby(['lat_grid', 'lon_grid'])['value'].mean().reset_index()
        
        geo_data['grid'][metal] = {
            'coordinates': grid_avg[['lat_grid', 'lon_grid', 'value']].to_dict('records')
        }
    
    return geo_data

@router.get("/stats/pca")
def get_pca_analysis(include_params: bool = Query(True), n_components: int = Query(3), db: Session = Depends(get_db)):
    """Perform Principal Component Analysis"""
    # Get all metal concentrations
    metals_data = db.query(MetalConcentration).all()
    if not metals_data:
        return {"error": "No metal concentration data found"}
    
    # Convert to wide format
    df = pd.DataFrame([{
        'sample_id': m.sample_id,
        'metal': m.metal,
        'value': m.value_mg_l
    } for m in metals_data])
    
    metals_wide = df.pivot(index='sample_id', columns='metal', values='value')
    
    # Add water quality parameters if requested
    if include_params:
        samples_data = db.query(Sample).all()
        for s in samples_data:
            if s.metadata_json:
                if 'ph' in s.metadata_json:
                    metals_wide.loc[s.id, 'pH'] = s.metadata_json['ph']
                if 'tds' in s.metadata_json:
                    metals_wide.loc[s.id, 'TDS'] = s.metadata_json['tds']
                if 'ec' in s.metadata_json:
                    metals_wide.loc[s.id, 'EC'] = s.metadata_json['ec']
    
    # Handle missing values
    metals_wide = metals_wide.fillna(metals_wide.mean())
    
    # Standardize data
    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(metals_wide)
    
    # Perform PCA
    pca = PCA(n_components=min(n_components, len(metals_wide.columns)))
    pca_result = pca.fit_transform(scaled_data)
    
    # Get loadings
    loadings = pd.DataFrame(
        pca.components_.T,
        columns=[f'PC{i+1}' for i in range(pca.n_components_)],
        index=metals_wide.columns
    )
    
    return {
        'explained_variance_ratio': pca.explained_variance_ratio_.tolist(),
        'cumulative_variance': np.cumsum(pca.explained_variance_ratio_).tolist(),
        'loadings': loadings.to_dict(),
        'sample_scores': pca_result.tolist(),
        'feature_names': metals_wide.columns.tolist()
    }

@router.get("/stats/cluster")
def get_cluster_analysis(k: int = Query(3, ge=2, le=10), include_params: bool = Query(True), pca_components: int = Query(2), db: Session = Depends(get_db)):
    """Perform K-means clustering analysis"""
    # Get all metal concentrations
    metals_data = db.query(MetalConcentration).all()
    if not metals_data:
        return {"error": "No metal concentration data found"}
    
    # Convert to wide format
    df = pd.DataFrame([{
        'sample_id': m.sample_id,
        'metal': m.metal,
        'value': m.value_mg_l
    } for m in metals_data])
    
    metals_wide = df.pivot(index='sample_id', columns='metal', values='value')
    
    # Add water quality parameters if requested
    if include_params:
        samples_data = db.query(Sample).all()
        for s in samples_data:
            if s.metadata_json:
                if 'ph' in s.metadata_json:
                    metals_wide.loc[s.id, 'pH'] = s.metadata_json['ph']
                if 'tds' in s.metadata_json:
                    metals_wide.loc[s.id, 'TDS'] = s.metadata_json['tds']
                if 'ec' in s.metadata_json:
                    metals_wide.loc[s.id, 'EC'] = s.metadata_json['ec']
    
    # Handle missing values
    metals_wide = metals_wide.fillna(metals_wide.mean())
    
    # Standardize data
    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(metals_wide)
    
    # Perform K-means clustering
    kmeans = KMeans(n_clusters=k, random_state=42)
    cluster_labels = kmeans.fit_predict(scaled_data)
    
    # Get 2D PCA for visualization
    pca = PCA(n_components=min(pca_components, len(metals_wide.columns)))
    pca_result = pca.fit_transform(scaled_data)
    
    # Create cluster membership table
    cluster_membership = []
    for i, (sample_id, cluster) in enumerate(zip(metals_wide.index, cluster_labels)):
        cluster_membership.append({
            'sample_id': int(sample_id),
            'cluster': int(cluster),
            'pc1': float(pca_result[i, 0]) if pca_result.shape[1] > 0 else 0,
            'pc2': float(pca_result[i, 1]) if pca_result.shape[1] > 1 else 0
        })
    
    return {
        'n_clusters': k,
        'cluster_centers': kmeans.cluster_centers_.tolist(),
        'cluster_membership': cluster_membership,
        'pca_explained_variance': pca.explained_variance_ratio_.tolist(),
        'feature_names': metals_wide.columns.tolist()
    }

@router.get("/stats/monthly")
def get_monthly_statistics(sample_id: int = Query(None), db: Session = Depends(get_db)):
    """Get monthly statistical analysis for metal concentrations"""
    from .services.stats import compute_monthly_statistics, format_monthly_statistics_table
    
    # Get time series data for the specified sample or all samples
    if sample_id:
        ts_rows = db.query(MetalTimeSeries).filter(MetalTimeSeries.sample_id == sample_id).all()
    else:
        ts_rows = db.query(MetalTimeSeries).all()
    
    if not ts_rows:
        return {"error": "No time series data found"}
    
    # Convert to timeseries format
    timeseries = {}
    for row in ts_rows:
        if row.metal not in timeseries:
            timeseries[row.metal] = {}
        timeseries[row.metal][row.period] = row.value_mg_l
    
    # Compute monthly statistics
    monthly_stats = compute_monthly_statistics(timeseries)
    
    # Format for frontend display
    formatted_table = format_monthly_statistics_table(monthly_stats)
    
    return formatted_table

@router.get("/stats/metal-indices")
def get_metal_indices_table(sample_id: int = Query(None), db: Session = Depends(get_db)):
    """Return compact metal indices table (avg vs limit, ratios) using monthly data.

    If sample_id is provided, uses its time series; otherwise aggregates all.
    """
    # Prefer dedicated time series table if present
    if sample_id:
        ts_rows = db.query(MetalTimeSeries).filter(MetalTimeSeries.sample_id == sample_id).all()
    else:
        ts_rows = db.query(MetalTimeSeries).all()

    if not ts_rows:
        return { 'error': 'No time series data found' }

    timeseries: Dict[str, Dict[str, float]] = {}
    for r in ts_rows:
        timeseries.setdefault(r.metal, {})[str(r.period)] = float(r.value_mg_l) if r.value_mg_l is not None else None

    return format_metal_indices_table(timeseries)

@router.get("/stats/metal-formulas")
def get_metal_formula_table(sample_id: int = Query(None), db: Session = Depends(get_db)):
    """Return per-metal values for each formula using mean monthly concentration."""
    if sample_id:
        ts_rows = db.query(MetalTimeSeries).filter(MetalTimeSeries.sample_id == sample_id).all()
    else:
        ts_rows = db.query(MetalTimeSeries).all()

    if not ts_rows:
        return { 'error': 'No time series data found' }

    timeseries: Dict[str, Dict[str, float]] = {}
    for r in ts_rows:
        timeseries.setdefault(r.metal, {})[str(r.period)] = float(r.value_mg_l) if r.value_mg_l is not None else None

    return format_metal_formula_table(timeseries)