from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit, LeaveOneGroupOut
from sklearn.pipeline import Pipeline

from .constants import (
    PEOPLE_COUNT_FEATURE_NAMES,
    PEOPLE_COUNT_FEATURE_SCHEMA_VERSION,
    PEOPLE_COUNT_MODEL_NAME,
    PEOPLE_COUNT_MODEL_VERSION,
)
from .dataset import build_training_table


def _metrics(y_true, y_pred) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    out = {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
    }
    if len(set(y_true.tolist())) > 1:
        out["r2"] = float(r2_score(y_true, y_pred))
    else:
        out["r2"] = float("nan")
    out["rounded_accuracy"] = float(np.mean(np.rint(y_pred).astype(int) == np.rint(y_true).astype(int)))
    return out


def build_model(random_state: int = 42) -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", RandomForestRegressor(
            n_estimators=300,
            random_state=random_state,
            min_samples_leaf=1,
            max_depth=None,
            n_jobs=-1,
        )),
    ])


def evaluate_group_holdout(model: Pipeline, X: pd.DataFrame, y: pd.Series, groups: pd.Series, random_state: int = 42) -> dict[str, Any]:
    unique_groups = sorted(set(groups.astype(str)))
    if len(unique_groups) < 2:
        return {"skipped": True, "reason": "Need at least 2 sessions/groups for holdout evaluation."}

    splitter = GroupShuffleSplit(n_splits=1, test_size=max(1 / len(unique_groups), 0.25), random_state=random_state)
    train_idx, test_idx = next(splitter.split(X, y, groups))
    m = clone(model)
    m.fit(X.iloc[train_idx], y.iloc[train_idx])
    pred = m.predict(X.iloc[test_idx])
    return {
        "skipped": False,
        "test_groups": sorted(set(groups.iloc[test_idx].astype(str))),
        "train_rows": int(len(train_idx)),
        "test_rows": int(len(test_idx)),
        "metrics": _metrics(y.iloc[test_idx], pred),
        "predictions": [
            {
                "row_index": int(i),
                "actual": float(a),
                "predicted": float(p),
                "predicted_rounded": int(max(0, round(float(p)))),
                "session_id": str(groups.iloc[i]),
            }
            for i, a, p in zip(test_idx, y.iloc[test_idx], pred)
        ],
    }


def evaluate_leave_one_group(model: Pipeline, X: pd.DataFrame, y: pd.Series, groups: pd.Series) -> dict[str, Any]:
    unique_groups = sorted(set(groups.astype(str)))
    if len(unique_groups) < 2:
        return {"skipped": True, "reason": "Need at least 2 sessions/groups for leave-one-group-out."}

    logo = LeaveOneGroupOut()
    all_actual: list[float] = []
    all_pred: list[float] = []
    fold_rows: list[dict[str, Any]] = []

    for fold, (train_idx, test_idx) in enumerate(logo.split(X, y, groups), start=1):
        m = clone(model)
        m.fit(X.iloc[train_idx], y.iloc[train_idx])
        pred = m.predict(X.iloc[test_idx])
        all_actual.extend(y.iloc[test_idx].astype(float).tolist())
        all_pred.extend(pred.astype(float).tolist())
        fold_rows.append({
            "fold": fold,
            "test_groups": sorted(set(groups.iloc[test_idx].astype(str))),
            "train_rows": int(len(train_idx)),
            "test_rows": int(len(test_idx)),
            "metrics": _metrics(y.iloc[test_idx], pred),
        })

    return {
        "skipped": False,
        "folds": fold_rows,
        "overall_metrics": _metrics(all_actual, all_pred),
    }


def train_people_count_model(
    dataset_root: str | Path,
    *,
    labels_path: str | Path | None = None,
    out_dir: str | Path = "artifacts/people_count_rf_custom",
    random_state: int = 42,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    train_df = build_training_table(dataset_root, labels_path=labels_path)
    X = train_df[PEOPLE_COUNT_FEATURE_NAMES].copy()
    y = train_df["people_count"].astype(float)
    groups = train_df["session_id"].astype(str)

    model = build_model(random_state=random_state)
    holdout = evaluate_group_holdout(model, X, y, groups, random_state=random_state)
    logo = evaluate_leave_one_group(model, X, y, groups)

    # Final model trained on all labelled data.
    model.fit(X, y)

    model_path = out_dir / "model.joblib"
    joblib.dump(model, model_path)

    feature_importance = pd.DataFrame({
        "feature": PEOPLE_COUNT_FEATURE_NAMES,
        "importance": model.named_steps["model"].feature_importances_,
    }).sort_values("importance", ascending=False)
    feature_importance.to_csv(out_dir / "feature_importance.csv", index=False)

    train_df.to_csv(out_dir / "training_table.csv", index=False)

    metadata = {
        "model_name": PEOPLE_COUNT_MODEL_NAME,
        "model_version": PEOPLE_COUNT_MODEL_VERSION,
        "feature_schema_version": PEOPLE_COUNT_FEATURE_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_root": str(dataset_root),
        "labels_path": str(labels_path) if labels_path else None,
        "training_rows": int(len(train_df)),
        "session_count": int(train_df["session_id"].nunique()),
        "target": "people_count",
        "target_min": float(y.min()),
        "target_max": float(y.max()),
        "feature_names": PEOPLE_COUNT_FEATURE_NAMES,
        "holdout_evaluation": holdout,
        "leave_one_group_out_evaluation": logo,
        "dataset_warning": (
            "This real dataset is small and session-correlated. Metrics are useful for smoke testing, "
            "not final accuracy claims. Collect more labelled sessions before relying on accuracy."
        ),
    }

    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "metrics.json").write_text(json.dumps({
        "holdout": holdout,
        "leave_one_group_out": logo,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return metadata
