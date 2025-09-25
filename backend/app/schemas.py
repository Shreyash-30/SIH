from typing import Dict, Optional, List
from pydantic import BaseModel

class ExtractedData(BaseModel):
    sample_id: Optional[str] = None
    collection_date: Optional[str] = None
    lab_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    metadata: Optional[str] = None  # JSON string or small text summary
    metals: Optional[Dict[str, float]] = None
    timeseries: Optional[Dict[str, Dict[str, float]]] = None  # metal -> {period -> value}
    sample_series: Optional[Dict[str, Dict[str, float]]] = None  # metal -> {sample_label -> value}
