from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import router as api_router
from .ml_api import router as ml_router
import os
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Water Quality Backend")
app.include_router(api_router, prefix="/api")
app.include_router(ml_router, prefix="/api")

# Serve ML artifacts (maps, charts) under /static/ml
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ML_DIR = os.path.join(_BASE_DIR, "storage", "ml")
os.makedirs(_ML_DIR, exist_ok=True)
app.mount("/static/ml", StaticFiles(directory=_ML_DIR), name="static_ml")

@app.get("/")
def health():
    return {"status": "ok"}

# CORS configuration
# You can override allowed origins with env var ALLOW_ORIGINS as a comma-separated list
# Example: ALLOW_ORIGINS=http://localhost:5173,http://192.168.0.10:5173
# To allow all origins (not recommended in production), set ALLOW_ORIGINS=*
_cors_env = os.getenv("ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").strip()
if _cors_env == "*":
    # When allowing all origins, FastAPI requires allow_credentials=False
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    allowed = [o.strip() for o in _cors_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
