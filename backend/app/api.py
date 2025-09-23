import os
import uuid
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from .database import get_db, Base, engine
from .services.extract import extract_file_data, detect_file_kind
from .models import Sample, MetalConcentration
from sqlalchemy.orm import Session
from .services.limits import get_limit_mg_l, get_weight, get_standard_id
from .services.indices import compute_indices
import pandas as pd
import numpy as np
import json
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

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
    assessments: Optional[Dict[str, Dict[str, float]]] = None
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
    assessments: Optional[Dict[str, Dict[str, float]]] = None
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

    db.commit()
    indices = compute_indices(extracted.metals or {}, exceed_count, severe_exceed)
    return UploadResponse(
        id=sample.id,
        file_path=dest_path,
        summary={"metals": metals_count},
        extracted_metals=extracted.metals or {},
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
    indices = compute_indices(metals or {}, exceed_count, severe_exceed) if metals else None
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
        assessments=assessments or None,
        indices=indices,
    )


@router.get("/stats/summary")
def stats_summary(db: Session = Depends(get_db)):
    rows = db.query(MetalConcentration).all()
    if not rows:
        return {"metals": {}}
    data = [{"metal": r.metal, "value_mg_l": r.value_mg_l} for r in rows if r.value_mg_l is not None]
    if not data:
        return {"metals": {}}
    df = pd.DataFrame(data)
    grouped = df.groupby("metal")["value_mg_l"]
    result = {}
    for metal, series in grouped:
        s = series.dropna().astype(float)
        if s.empty:
            continue
        mean = float(s.mean())
        median = float(s.median())
        std = float(s.std(ddof=1)) if len(s) > 1 else 0.0
        var = float(s.var(ddof=1)) if len(s) > 1 else 0.0
        min_v = float(s.min())
        max_v = float(s.max())
        q1 = float(s.quantile(0.25))
        q3 = float(s.quantile(0.75))
        counts, bin_edges = np.histogram(s.values, bins=10)
        limit = get_limit_mg_l(metal)
        exceed_pct = float(((s > limit).sum() / len(s)) * 100.0) if limit is not None else None
        result[metal] = {
            "count": int(len(s)),
            "mean": mean,
            "median": median,
            "std": std,
            "var": var,
            "min": min_v,
            "max": max_v,
            "exceed_pct": exceed_pct,
            "limit_mg_l": float(limit) if limit is not None else None,
            "histogram": {"counts": [int(c) for c in counts.tolist()], "bins": [float(b) for b in bin_edges.tolist()]},
            "box": {"min": min_v, "q1": q1, "median": median, "q3": q3, "max": max_v},
        }
    return {"metals": result}


@router.get("/stats/correlation")
def stats_correlation(db: Session = Depends(get_db), method: str = "pearson"):
    method = method.lower()
    if method not in ("pearson", "spearman"):
        method = "pearson"
    samples = db.query(Sample).all()
    if not samples:
        return {"variables": [], "pearson": [], "spearman": [], "strong": []}
    rows = []
    for s in samples:
        row = {"_sample_id": s.id}
        try:
            if s.metadata_json:
                meta = json.loads(s.metadata_json)
                if isinstance(meta, dict):
                    row["pH"] = meta.get("pH")
                    row["TDS_mg_L"] = meta.get("TDS_mg_L")
                    row["EC_mS_cm"] = meta.get("EC_mS_cm")
        except Exception:
            pass
        mrows = db.query(MetalConcentration).filter(MetalConcentration.sample_id == s.id).all()
        for mr in mrows:
            row[mr.metal] = mr.value_mg_l
        rows.append(row)
    if not rows:
        return {"variables": [], "pearson": [], "spearman": [], "strong": []}
    df = pd.DataFrame(rows).drop(columns=["_sample_id"], errors="ignore")
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(axis=1, how="all")
    variables = df.columns.tolist()
    if not variables:
        return {"variables": [], "pearson": [], "spearman": [], "strong": []}
    pearson = df.corr(method="pearson").fillna(0.0)
    spearman = df.corr(method="spearman").fillna(0.0)
    strong_pairs = []
    threshold = 0.7
    corr_mat = pearson if method == "pearson" else spearman
    for i, a in enumerate(variables):
        for j, b in enumerate(variables):
            if j <= i:
                continue
            r = float(corr_mat.loc[a, b])
            if abs(r) >= threshold:
                strong_pairs.append({"a": a, "b": b, "r": r, "method": method})
    return {"variables": variables, "pearson": pearson.values.tolist(), "spearman": spearman.values.tolist(), "strong": strong_pairs}


@router.get("/stats/trends")
def stats_trends(db: Session = Depends(get_db)):
    samples = db.query(Sample).all()
    if not samples:
        return {"metals": {}}
    sample_meta = {}
    for s in samples:
        date = s.collection_date
        if not date and s.metadata_json:
            try:
                meta = json.loads(s.metadata_json)
                if isinstance(meta, dict):
                    date = meta.get("collection_date") or meta.get("date")
            except Exception:
                pass
        sample_meta[s.id] = {"date": date}
    mrows = db.query(MetalConcentration).all()
    data = []
    for r in mrows:
        info = sample_meta.get(r.sample_id, {})
        data.append({"sample_id": r.sample_id, "metal": r.metal, "value_mg_l": r.value_mg_l, "date": info.get("date")})
    if not data:
        return {"metals": {}}
    df = pd.DataFrame(data)
    df["_dt"] = pd.to_datetime(df["date"], errors="coerce")
    result = {}
    for metal, sub in df.groupby("metal"):
        s = sub.dropna(subset=["_dt"]).copy()
        if s.empty:
            continue
        agg = s.groupby("_dt")["value_mg_l"].mean().reset_index().sort_values("_dt")
        result[metal] = {"dates": agg["_dt"].dt.strftime("%Y-%m-%d").tolist(), "values": [float(v) if v is not None else None for v in agg["value_mg_l"].tolist()]}
    return {"metals": result}


@router.get("/stats/geo")
def stats_geo(db: Session = Depends(get_db), grid: int = 0):
    samples = db.query(Sample).all()
    if not samples:
        return {"points": [], "grid": None}
    points = []
    for s in samples:
        if s.latitude is None or s.longitude is None:
            continue
        mrows = db.query(MetalConcentration).filter(MetalConcentration.sample_id == s.id).all()
        metals = {r.metal: r.value_mg_l for r in mrows}
        points.append({"id": s.id, "lat": s.latitude, "lng": s.longitude, "metals": metals})
    grid_result = None
    if grid and grid > 0 and len(points) > 1:
        cell = float(grid) / 111000.0
        def key(lat, lng):
            return (int(lat // cell), int(lng // cell))
        buckets = {}
        for p in points:
            k = key(p["lat"], p["lng"])
            b = buckets.setdefault(k, {"lat": [], "lng": [], "count": 0, "metals": {}})
            b["lat"].append(p["lat"])
            b["lng"].append(p["lng"])
            b["count"] += 1
            for m, v in (p["metals"] or {}).items():
                if v is None:
                    continue
                arr = b["metals"].setdefault(m, [])
                arr.append(v)
        grid_cells = []
        for (_, _), b in buckets.items():
            center_lat = float(np.mean(b["lat"])) if b["lat"] else None
            center_lng = float(np.mean(b["lng"])) if b["lng"] else None
            metal_means = {m: float(np.mean(vals)) for m, vals in b["metals"].items() if vals}
            grid_cells.append({"center_lat": center_lat, "center_lng": center_lng, "count": b["count"], "means": metal_means})
        grid_result = grid_cells
    return {"points": points, "grid": grid_result}


@router.get("/stats/pca")
def stats_pca(db: Session = Depends(get_db), include_params: bool = True, n_components: int = 3):
    samples = db.query(Sample).all()
    if not samples:
        return {"variables": [], "explained_variance_ratio": [], "components": [], "scores": [], "sample_ids": []}
    rows = []
    for s in samples:
        row = {"_id": s.id}
        if include_params and s.metadata_json:
            try:
                meta = json.loads(s.metadata_json)
                if isinstance(meta, dict):
                    row["pH"] = meta.get("pH")
                    row["TDS_mg_L"] = meta.get("TDS_mg_L")
                    row["EC_mS_cm"] = meta.get("EC_mS_cm")
            except Exception:
                pass
        mrows = db.query(MetalConcentration).filter(MetalConcentration.sample_id == s.id).all()
        for mr in mrows:
            row[mr.metal] = mr.value_mg_l
        rows.append(row)
    if not rows:
        return {"variables": [], "explained_variance_ratio": [], "components": [], "scores": [], "sample_ids": []}
    df = pd.DataFrame(rows).set_index("_id")
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
    if df.shape[1] == 0 or df.shape[0] < 2:
        return {"variables": df.columns.tolist(), "explained_variance_ratio": [], "components": [], "scores": [], "sample_ids": df.index.tolist()}
    variables = df.columns.tolist()
    df_imputed = df.fillna(df.mean(numeric_only=True))
    scaler = StandardScaler()
    X = scaler.fit_transform(df_imputed.values)
    pca = PCA(n_components=min(n_components, X.shape[1]))
    scores = pca.fit_transform(X)
    components = pca.components_
    evr = pca.explained_variance_ratio_
    return {"variables": variables, "explained_variance_ratio": [float(x) for x in evr.tolist()], "components": [[float(x) for x in row] for row in components.tolist()], "scores": [[float(x) for x in row] for row in scores.tolist()], "sample_ids": [int(i) for i in df_imputed.index.tolist()]}


@router.get("/stats/cluster")
def stats_cluster(db: Session = Depends(get_db), k: int = 3, include_params: bool = True, pca_components: int = 2, seed: int = 42):
    samples = db.query(Sample).all()
    if not samples:
        return {"sample_ids": [], "labels": [], "centers": [], "variables": [], "pca2": None}
    rows = []
    for s in samples:
        row = {"_id": s.id}
        if include_params and s.metadata_json:
            try:
                meta = json.loads(s.metadata_json)
                if isinstance(meta, dict):
                    row["pH"] = meta.get("pH")
                    row["TDS_mg_L"] = meta.get("TDS_mg_L")
                    row["EC_mS_cm"] = meta.get("EC_mS_cm")
            except Exception:
                pass
        mrows = db.query(MetalConcentration).filter(MetalConcentration.sample_id == s.id).all()
        for mr in mrows:
            row[mr.metal] = mr.value_mg_l
        rows.append(row)
    df = pd.DataFrame(rows).set_index("_id")
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
    if df.shape[1] == 0 or df.shape[0] < 2:
        return {"sample_ids": df.index.tolist(), "labels": [], "centers": [], "variables": df.columns.tolist(), "pca2": None}
    variables = df.columns.tolist()
    df_imputed = df.fillna(df.mean(numeric_only=True))
    scaler = StandardScaler()
    X = scaler.fit_transform(df_imputed.values)
    k = max(2, int(k))
    kmeans = KMeans(n_clusters=k, n_init=10, random_state=seed)
    labels = kmeans.fit_predict(X)
    centers = kmeans.cluster_centers_
    pca2 = None
    try:
        pca = PCA(n_components=min(max(2, pca_components), X.shape[1]))
        scores2 = pca.fit_transform(X)
        pca2 = {"scores": [[float(x) for x in row] for row in scores2[:, :2].tolist()], "explained_variance_ratio": [float(x) for x in pca.explained_variance_ratio_[:2].tolist()]}
    except Exception:
        pca2 = None
    return {"sample_ids": [int(i) for i in df_imputed.index.tolist()], "variables": variables, "labels": [int(l) for l in labels.tolist()], "centers": [[float(x) for x in row] for row in centers.tolist()], "pca2": pca2}
