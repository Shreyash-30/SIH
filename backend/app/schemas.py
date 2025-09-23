from typing import Dict, Optional
from pydantic import BaseModel

class ExtractedData(BaseModel):
    sample_id: Optional[str] = None
    collection_date: Optional[str] = None
    lab_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    metadata: Optional[str] = None  # JSON string or small text summary
    metals: Optional[Dict[str, float]] = None
    # Detailed per-metal info for audit and further processing
    metals_detail: Optional[Dict[str, Dict[str, Optional[float]]]] = None
