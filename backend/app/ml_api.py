from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .database import get_db
from .services.ml import (
    assemble_dataset,
    train_regressors,
    train_classifier,
    run_kmeans,
    forecast_timeseries,
    generate_hotspot_map,
)

router = APIRouter()


@router.get("/ml/dataset")
def ml_preview_dataset(limit: int = Query(50), db: Session = Depends(get_db)) -> Any:
    """Preview the assembled ML dataset (features per sample)."""
    try:
        df = assemble_dataset(db)
        df_prev = df.head(limit).fillna(None)
        return {
            "columns": [str(c) for c in df_prev.columns],
            "index": [int(i) for i in df_prev.index.tolist()],
            "rows": df_prev.reset_index().to_dict(orient="records"),
            "shape": [int(df.shape[0]), int(df.shape[1])],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to assemble dataset: {e}")


@router.post("/ml/train/regression")
def ml_train_regression(
    target: str = Query("HPI", description="Target index to predict, e.g., HPI/HEI/HI/Cd/CDI/MI"),
    test_size: float = Query(0.2, ge=0.1, le=0.9),
    random_state: int = Query(42),
    db: Session = Depends(get_db),
) -> Any:
    """Train multivariate regressors (Linear, RandomForest) to predict a target index."""
    try:
        results = train_regressors(db, target=target, test_size=test_size, random_state=random_state)
        return {"target": target.upper(), "results": results}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {e}")


@router.post("/ml/train/classifier")
def ml_train_classifier(
    target: str = Query("HPI", description="Target index to classify into risk levels (e.g., Safe/Moderate/Unsafe for HPI)"),
    test_size: float = Query(0.2, ge=0.1, le=0.9),
    random_state: int = Query(42),
    db: Session = Depends(get_db),
) -> Any:
    """Train RandomForest classifier for categorical water quality risk levels."""
    try:
        results = train_classifier(db, target=target, test_size=test_size, random_state=random_state)
        return {"target": target.upper(), "results": results}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {e}")


@router.post("/ml/cluster")
def ml_cluster(
    k: int = Query(3, ge=2, le=20),
    random_state: int = Query(42),
    db: Session = Depends(get_db),
) -> Any:
    """Run K-means clustering on the assembled dataset and return labels per sample."""
    try:
        results = run_kmeans(db, k=k, random_state=random_state)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clustering failed: {e}")


@router.get("/ml/forecast")
def ml_forecast(
    sample_id: int = Query(..., description="Sample ID to forecast for"),
    target: str = Query("HPI", description="Target index or metal name to forecast"),
    horizon: int = Query(6, ge=1, le=24),
    model: str = Query("auto", description="Model: auto|linear|poly2|gbr"),
    db: Session = Depends(get_db),
) -> Any:
    """Forecast the next `horizon` periods for a target series (e.g., HPI) for a given sample.

    Returns history, forecast values, CI bounds, flagged months (if HPI threshold exceeded), and plot path.
    """
    try:
        result = forecast_timeseries(db, sample_id=sample_id, target=target, horizon=horizon, model=model)
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Forecast failed: {e}")


@router.get("/ml/hotspot")
def ml_hotspot(
    target: str = Query("HPI", description="Target metric: HPI/HEI/HI/Cd/CDI/MI or metal symbol/name"),
    use_forecast: bool = Query(False),
    horizon: int = Query(1, ge=1, le=24),
    country: str = Query(None, description="Optional country hint like 'india' to focus/fit map"),
    heatmap: bool = Query(True, description="Include heatmap overlay"),
    db: Session = Depends(get_db),
):
    """Generate an interactive hotspot map (HTML) for the requested target.

    If use_forecast=True, uses next-horizon forecast values per sample; otherwise current values.
    Returns path to saved HTML and point data.
    """
    try:
        res = generate_hotspot_map(
            db,
            target=target,
            use_forecast=use_forecast,
            horizon=horizon,
            country=country,
            heatmap=heatmap,
        )
        # Always return 200 with payload; if an 'error' key exists, frontend can display it.
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Hotspot generation failed: {e}")
