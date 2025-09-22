import os
import re
import json
from typing import Dict, Tuple, Optional
import pandas as pd
from pdfminer.high_level import extract_text
from ..schemas import ExtractedData

ND_PAT = re.compile(r"^(ND|N/D|NA|N\.?D\.?)$", re.IGNORECASE)

UNIT_MAP = {
    "mg/l": 1.0,
    "mg/L": 1.0,
    "ug/l": 1e-3,
    "µg/l": 1e-3,
}

METAL_ALIASES = {
    "cadmium": "Cd",
    "cd": "Cd",
    "lead": "Pb",
    "pb": "Pb",
    "mercury": "Hg",
    "hg": "Hg",
    "arsenic": "As",
    "as": "As",
    "chromium": "Cr",
    "cr": "Cr",
    "nickel": "Ni",
    "ni": "Ni",
}

LOD_POLICY = "zero"  # 'zero' or 'half'


def detect_file_kind(filename: str, content_type: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in [".csv"]:
        return "csv"
    if ext in [".xls", ".xlsx"]:
        return "excel"
    if ext in [".pdf"]:
        return "pdf"
    if "csv" in content_type:
        return "csv"
    if "excel" in content_type or "sheet" in content_type:
        return "excel"
    if "pdf" in content_type:
        return "pdf"
    return "csv"


def normalize_value(value, unit: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        if ND_PAT.match(v):
            return 0.0 if LOD_POLICY == "zero" else None
        try:
            value = float(v)
        except Exception:
            return None
    factor = UNIT_MAP.get((unit or "mg/l").lower(), 1.0)
    return float(value) * factor


def _first_numeric(series: pd.Series) -> Optional[float]:
    for raw in series:
        num = normalize_value(raw, None)
        if num is not None:
            return num
    return None


def _first_float(series: pd.Series) -> Optional[float]:
    for raw in series:
        try:
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                continue
            return float(str(raw).strip())
        except Exception:
            continue
    return None


def _match_alias(text: str) -> Optional[str]:
    lower = str(text).strip().lower()
    for key, alias in METAL_ALIASES.items():
        if key in lower or lower == alias.lower():
            return alias
    return None


def parse_dataframe(df: pd.DataFrame) -> Tuple[Dict[str, float], dict]:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    metals: Dict[str, float] = {}
    info: dict = {"sample_id": None, "collection_date": None, "lab_name": None, "latitude": None, "longitude": None, "pH": None, "TDS_mg_L": None, "EC_mS_cm": None}

    # Basic info
    for col in df.columns:
        lower = col.lower()
        if lower in ["sampleid", "sample id", "sample_id", "id"] and not info["sample_id"]:
            ser = df[col].dropna()
            info["sample_id"] = str(ser.iloc[0]) if not ser.empty else None
        if "date" in lower and not info["collection_date"]:
            ser = df[col].dropna()
            info["collection_date"] = str(ser.iloc[0]) if not ser.empty else None
        if any(k in lower for k in ["lab", "source"]) and not info["lab_name"]:
            ser = df[col].dropna()
            info["lab_name"] = str(ser.iloc[0]) if not ser.empty else None
        if "latitude" in lower and info["latitude"] is None:
            info["latitude"] = _first_float(df[col])
        if "longitude" in lower and info["longitude"] is None:
            info["longitude"] = _first_float(df[col])
        if lower in ["ph", "pH".lower()] and info["pH"] is None:
            info["pH"] = _first_float(df[col])
        if "tds" in lower and info["TDS_mg_L"] is None:
            # assume mg/L unless unit column provided separately
            info["TDS_mg_L"] = _first_float(df[col])
        if lower in ["ec", "electrical conductivity", "conductivity"] and info["EC_mS_cm"] is None:
            info["EC_mS_cm"] = _first_float(df[col])

    # Wide format metals
    for col in df.columns:
        alias = _match_alias(col)
        if alias and alias not in metals:
            num = _first_numeric(df[col])
            if num is not None:
                metals[alias] = num

    # Long format (parameter/value/unit)
    param_col = None
    value_col = None
    unit_col = None
    for col in df.columns:
        l = col.lower()
        if param_col is None and any(k in l for k in ["parameter", "analyte", "metal", "test", "name"]):
            param_col = col
        if value_col is None and any(k in l for k in ["value", "result", "concentration", "conc", "amount"]):
            value_col = col
        if unit_col is None and "unit" in l:
            unit_col = col

    if param_col and value_col:
        for _, row in df.iterrows():
            alias = _match_alias(row.get(param_col, ""))
            if not alias:
                continue
            raw_val = row.get(value_col)
            unit = row.get(unit_col) if unit_col else None
            num = normalize_value(raw_val, str(unit) if unit is not None else None)
            if num is not None:
                metals[alias] = num

    # Pack metadata
    meta_payload = {}
    for key in ["sample_id", "collection_date", "lab_name", "pH", "TDS_mg_L", "EC_mS_cm"]:
        if info.get(key) is not None and info.get(key) != "":
            meta_payload[key] = info[key]

    return metals, {**info, "_meta_json": json.dumps(meta_payload) if meta_payload else None}


def extract_from_csv_excel(path: str) -> ExtractedData:
    df = pd.read_csv(path) if path.lower().endswith(".csv") else pd.read_excel(path)
    metals, info = parse_dataframe(df)
    return ExtractedData(
        sample_id=info.get("sample_id"),
        collection_date=info.get("collection_date"),
        lab_name=info.get("lab_name"),
        latitude=info.get("latitude"),
        longitude=info.get("longitude"),
        metadata=info.get("_meta_json"),
        metals={k: v for k, v in metals.items() if v is not None},
    )


def extract_from_pdf(path: str) -> ExtractedData:
    text = extract_text(path)
    meta = {}
    sample_id = None
    lab = None
    date = None

    for name, alias in METAL_ALIASES.items():
        pattern = re.compile(rf"\b{name}\b\s*[:\-]?\s*([0-9.]+)\s*(mg/l|ug/l|µg/l)?", re.IGNORECASE)
        m = pattern.search(text)
        if m:
            value_raw = m.group(1)
            unit = m.group(2) or "mg/l"
            val = normalize_value(value_raw, unit)
            if val is not None:
                meta.setdefault("metals", {})[alias] = val

    sid = re.search(r"Sample\s*ID\s*[:\-]?\s*([A-Za-z0-9_-]+)", text, re.IGNORECASE)
    if sid:
        sample_id = sid.group(1)
    dat = re.search(r"Date\s*[:\-]?\s*([0-9]{2,4}[\-/][0-9]{1,2}[\-/][0-9]{1,2})", text, re.IGNORECASE)
    if dat:
        date = dat.group(1)

    metals = meta.get("metals", {})
    return ExtractedData(
        sample_id=sample_id,
        collection_date=date,
        lab_name=lab,
        metadata=json.dumps({k: v for k, v in meta.items() if k != 'metals'}) if meta else None,
        metals=metals,
    )


def extract_file_data(path: str, kind: str) -> ExtractedData:
    if kind in ("csv", "excel"):
        return extract_from_csv_excel(path)
    if kind == "pdf":
        return extract_from_pdf(path)
    return extract_from_csv_excel(path)
