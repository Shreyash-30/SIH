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
