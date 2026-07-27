from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import LeaveOneGroupOut

from .constants import FEATURE_NAMES, MODEL_NAME, MODEL_VERSION, PEOPLE_COUNT_FEATURE_SCHEMA_VERSION
from .dataset import build_training_table
from .predictor import occupancy_level_from_count
from .train import build_model


def _rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def regression_metrics(y_true: pd.Series | np.ndarray, y_pred: pd.Series | np.ndarray) -> dict[str, float]:
    y_true_arr = np.asarray(y_true, dtype=float)
    y_pred_arr = np.asarray(y_pred, dtype=float)

    rounded_true = np.rint(y_true_arr).astype(int)
    rounded_pred = np.rint(y_pred_arr).astype(int)

    metrics = {
        "mae": float(mean_absolute_error(y_true_arr, y_pred_arr)),
        "rmse": _rmse(y_true_arr, y_pred_arr),
        "mean_error": float(np.mean(y_pred_arr - y_true_arr)),
        "rounded_accuracy": float(np.mean(rounded_true == rounded_pred)),
    }
    if len(np.unique(y_true_arr)) > 1:
        metrics["r2"] = float(r2_score(y_true_arr, y_pred_arr))
    else:
        metrics["r2"] = float("nan")
    return metrics


def _safe_label(row: pd.Series) -> str:
    if "label" in row and pd.notna(row["label"]):
        return str(row["label"])
    if "session_label" in row and pd.notna(row["session_label"]):
        return str(row["session_label"])
    return ""


def evaluate_leave_one_session(
    dataset_root: str | Path,
    *,
    labels_path: str | Path | None = None,
    out_dir: str | Path = "outputs/leave_one_session",
    random_state: int = 42,
    save_fold_models: bool = False,
) -> dict[str, Any]:
    """Run leave-one-session-out evaluation.

    This is the strict evaluation mode for the current dataset because windows
    inside one session are highly similar. Each fold trains on all sessions
    except one and tests on the completely held-out session.

    Outputs:
    - leave_one_session_predictions.csv
    - leave_one_session_metrics_by_session.csv
    - leave_one_session_metrics_overall.json
    - leave_one_session_confusion_matrix.csv
    - optional fold_models/fold_XX_model.joblib
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = build_training_table(dataset_root, labels_path=labels_path)
    if "session_id" not in df.columns:
        raise ValueError("Training table must include session_id for leave-one-session evaluation.")

    X = df[FEATURE_NAMES].copy()
    y = df["people_count"].astype(float)
    groups = df["session_id"].astype(str)

    unique_sessions = sorted(groups.unique().tolist())
    if len(unique_sessions) < 2:
        raise ValueError("Leave-one-session evaluation needs at least 2 sessions.")

    base_model = build_model(random_state=random_state)
    logo = LeaveOneGroupOut()

    prediction_rows: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []

    for fold_index, (train_idx, test_idx) in enumerate(logo.split(X, y, groups), start=1):
        model = clone(base_model)
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        pred = model.predict(X.iloc[test_idx])

        test_df = df.iloc[test_idx].copy().reset_index(drop=True)
        test_session_id = str(test_df["session_id"].iloc[0])
        test_label = _safe_label(test_df.iloc[0])
        fold_metrics = regression_metrics(test_df["people_count"], pred)

        fold_rows.append({
            "fold": fold_index,
            "test_session_id": test_session_id,
            "test_label": test_label,
            "actual_people_count": float(test_df["people_count"].iloc[0]),
            "train_rows": int(len(train_idx)),
            "test_rows": int(len(test_idx)),
            "predicted_mean": float(np.mean(pred)),
            "predicted_min": float(np.min(pred)),
            "predicted_max": float(np.max(pred)),
            **fold_metrics,
        })

        if save_fold_models:
            fold_model_dir = out_dir / "fold_models"
            fold_model_dir.mkdir(parents=True, exist_ok=True)
            joblib.dump(model, fold_model_dir / f"fold_{fold_index:02d}_{test_session_id}.joblib")

        for row, pred_value in zip(test_df.to_dict(orient="records"), pred):
            pred_float = float(pred_value)
            pred_rounded = int(max(0, round(pred_float)))
            prediction_rows.append({
                "fold": fold_index,
                "test_session_id": test_session_id,
                "window_id": row.get("window_id", ""),
                "room_id": row.get("room_id", ""),
                "device_id": row.get("device_id", ""),
                "window_start": row.get("window_start", ""),
                "window_end": row.get("window_end", ""),
                "label": row.get("label", row.get("session_label", "")),
                "actual_people_count": float(row["people_count"]),
                "predicted_people_count": pred_float,
                "predicted_people_count_rounded": pred_rounded,
                "occupancy_level": occupancy_level_from_count(pred_rounded),
                "error": pred_float - float(row["people_count"]),
                "absolute_error": abs(pred_float - float(row["people_count"])),
                "rounded_correct": pred_rounded == int(round(float(row["people_count"]))),
            })

    predictions_df = pd.DataFrame(prediction_rows)
    by_session_df = pd.DataFrame(fold_rows)

    overall_metrics = regression_metrics(
        predictions_df["actual_people_count"],
        predictions_df["predicted_people_count"],
    )

    confusion = pd.crosstab(
        predictions_df["actual_people_count"].astype(int),
        predictions_df["predicted_people_count_rounded"].astype(int),
        rownames=["actual_people_count"],
        colnames=["predicted_people_count_rounded"],
    )

    predictions_df.to_csv(out_dir / "leave_one_session_predictions.csv", index=False)
    by_session_df.to_csv(out_dir / "leave_one_session_metrics_by_session.csv", index=False)
    confusion.to_csv(out_dir / "leave_one_session_confusion_matrix.csv")

    summary = {
        "evaluation_name": "leave_one_session_out",
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "feature_schema_version": PEOPLE_COUNT_FEATURE_SCHEMA_VERSION,
        "dataset_root": str(dataset_root),
        "labels_path": str(labels_path) if labels_path else None,
        "session_count": int(len(unique_sessions)),
        "window_count": int(len(df)),
        "feature_count": int(len(FEATURE_NAMES)),
        "overall_metrics": overall_metrics,
        "folds": fold_rows,
        "interpretation": (
            "This is the most trustworthy evaluation for the current small dataset. "
            "Each fold holds out one full session, so test windows are not from the same "
            "continuous capture as the training windows."
        ),
    }
    (out_dir / "leave_one_session_metrics_overall.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=True),
        encoding="utf-8",
    )

    _write_markdown_report(out_dir, summary, by_session_df, confusion)
    _write_html_report(out_dir, summary, by_session_df, confusion)
    _write_charts(out_dir, predictions_df, by_session_df, confusion)

    return summary


def _write_markdown_report(
    out_dir: Path,
    summary: dict[str, Any],
    by_session_df: pd.DataFrame,
    confusion: pd.DataFrame,
) -> None:
    m = summary["overall_metrics"]
    md = f"""# Leave-one-session-out Evaluation

## Overall metrics

- Sessions: {summary["session_count"]}
- Windows: {summary["window_count"]}
- MAE: {m["mae"]:.4f}
- RMSE: {m["rmse"]:.4f}
- Mean error: {m["mean_error"]:.4f}
- Rounded accuracy: {m["rounded_accuracy"]:.2%}
- R2: {m["r2"]:.4f}

## Why this matters

This evaluation is stricter than checking predictions on the same sessions used
for training. Each fold trains on all sessions except one and tests on the
completely held-out session.

## Per-session metrics

{by_session_df.to_markdown(index=False)}

## Confusion matrix

{confusion.to_markdown()}
"""
    (out_dir / "leave_one_session_report.md").write_text(md, encoding="utf-8")


def _write_html_report(
    out_dir: Path,
    summary: dict[str, Any],
    by_session_df: pd.DataFrame,
    confusion: pd.DataFrame,
) -> None:
    m = summary["overall_metrics"]

    table = by_session_df.copy()
    for col in ["mae", "rmse", "mean_error", "rounded_accuracy", "r2", "predicted_mean", "predicted_min", "predicted_max"]:
        if col in table.columns:
            table[col] = table[col].map(lambda x: "N/A" if pd.isna(x) else f"{float(x):.4f}")

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Leave-one-session-out Evaluation</title>
<style>
body {{
  margin: 0;
  background: #f6f7fb;
  color: #1f2937;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, "Noto Sans SC", sans-serif;
}}
.wrapper {{
  max-width: 1120px;
  margin: 0 auto;
  padding: 32px 24px 48px;
}}
.hero, .card {{
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 20px;
  padding: 22px;
  margin-bottom: 16px;
}}
h1 {{ margin: 0 0 8px; }}
.grid {{
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}}
.metric {{
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 18px;
  padding: 16px;
}}
.metric-label {{ color: #6b7280; font-size: 13px; }}
.metric-value {{ font-size: 28px; font-weight: 700; margin-top: 4px; }}
img {{
  width: 100%;
  display: block;
  border-radius: 14px;
  border: 1px solid #e5e7eb;
  background: #fff;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  font-size: 13px;
}}
th, td {{
  border-bottom: 1px solid #e5e7eb;
  padding: 9px 10px;
  text-align: left;
}}
th {{ background: #f3f4f6; }}
.note {{
  border-left: 5px solid #9ca3af;
  background: #fff;
  border-radius: 14px;
  padding: 14px 16px;
  margin: 16px 0;
  line-height: 1.6;
}}
@media (max-width: 800px) {{
  .grid {{ grid-template-columns: 1fr 1fr; }}
}}
</style>
</head>
<body>
<div class="wrapper">
  <section class="hero">
    <h1>Leave-one-session-out Evaluation</h1>
    <p>每一轮保留一个完整 session 作为测试集，其余 session 训练模型。这个结果比同 session 预测更接近真实泛化效果。</p>
  </section>

  <section class="grid">
    <div class="metric"><div class="metric-label">Sessions</div><div class="metric-value">{summary["session_count"]}</div></div>
    <div class="metric"><div class="metric-label">Windows</div><div class="metric-value">{summary["window_count"]}</div></div>
    <div class="metric"><div class="metric-label">MAE</div><div class="metric-value">{m["mae"]:.3f}</div></div>
    <div class="metric"><div class="metric-label">Rounded accuracy</div><div class="metric-value">{m["rounded_accuracy"]:.0%}</div></div>
  </section>

  <div class="note">
    <strong>解读：</strong>MAE={m["mae"]:.3f}，RMSE={m["rmse"]:.3f}，四舍五入准确率={m["rounded_accuracy"]:.0%}。
    如果同 session 预测是 100%，但 leave-one-session 明显更低，应以后者作为更真实的模型效果。
  </div>

  <section class="card">
    <h2>Per-session metrics</h2>
    {table.to_html(index=False)}
  </section>

  <section class="card">
    <h2>Charts</h2>
    <h3>Actual vs predicted</h3>
    <img src="charts/leave_one_session_actual_vs_predicted.png" alt="Actual vs predicted">
    <h3>MAE by held-out session</h3>
    <img src="charts/leave_one_session_mae_by_session.png" alt="MAE by held-out session">
    <h3>Confusion matrix</h3>
    <img src="charts/leave_one_session_confusion_matrix.png" alt="Confusion matrix">
  </section>
</div>
</body>
</html>"""
    (out_dir / "leave_one_session_report.html").write_text(html, encoding="utf-8")


def _write_charts(out_dir: Path, predictions_df: pd.DataFrame, by_session_df: pd.DataFrame, confusion: pd.DataFrame) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return

    chart_dir = out_dir / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    plot = predictions_df.copy()
    plot["global_index"] = range(1, len(plot) + 1)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(plot["global_index"], plot["actual_people_count"], marker="o", label="Actual")
    ax.plot(plot["global_index"], plot["predicted_people_count"], marker="o", label="Predicted")
    ax.set_title("Leave-one-session-out: actual vs predicted")
    ax.set_xlabel("Held-out window index")
    ax.set_ylabel("People count")
    ax.legend()
    fig.tight_layout()
    fig.savefig(chart_dir / "leave_one_session_actual_vs_predicted.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    chart_df = by_session_df.copy()
    chart_df["label_short"] = chart_df["test_label"].astype(str).str.replace("_", "\n", regex=False)
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(chart_df["label_short"], chart_df["mae"])
    ax.set_title("Leave-one-session-out MAE by held-out session")
    ax.set_xlabel("Held-out session")
    ax.set_ylabel("MAE")
    for i, v in enumerate(chart_df["mae"]):
        ax.text(i, v + 0.01, f"{v:.3f}", ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(chart_dir / "leave_one_session_mae_by_session.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(confusion.values)
    ax.set_title("Leave-one-session-out rounded confusion matrix")
    ax.set_xlabel("Predicted count")
    ax.set_ylabel("Actual count")
    ax.set_xticks(range(len(confusion.columns)))
    ax.set_yticks(range(len(confusion.index)))
    ax.set_xticklabels(confusion.columns)
    ax.set_yticklabels(confusion.index)
    for i in range(confusion.shape[0]):
        for j in range(confusion.shape[1]):
            ax.text(j, i, int(confusion.values[i, j]), ha="center", va="center")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(chart_dir / "leave_one_session_confusion_matrix.png", dpi=220, bbox_inches="tight")
    plt.close(fig)
