import json
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "outputs"
JSON_PATH = OUTPUT_DIR / "optimization_results.json"


def initialize_optimization_results_db():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not JSON_PATH.exists():
        JSON_PATH.write_text("[]", encoding="utf-8")


def _load_runs():
    initialize_optimization_results_db()
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        return []

    return data


def save_optimization_run(results, summary, input_snapshot, mode, excel_path=None):
    runs = _load_runs()
    run_id = max((run.get("run_id", 0) for run in runs), default=0) + 1

    member_rows = []
    for result in results:
        member_rows.append(
            {
                "member_type": "Beam",
                "storey": int(result["storey"]),
                "section_name": result["beam_section"],
                "steel_grade": result["beam_grade"],
                "utilization_ratio": float(result["beam_utilization"]),
                "member_cost_SGD": float(result["beam_cost_SGD"]),
                "payload": result,
            }
        )
        member_rows.append(
            {
                "member_type": "Column",
                "storey": int(result["storey"]),
                "section_name": result["column_section"],
                "steel_grade": result["column_grade"],
                "utilization_ratio": float(result["column_utilization"]),
                "member_cost_SGD": float(result["column_left_cost_SGD"] + result["column_right_cost_SGD"]),
                "payload": result,
            }
        )

    runs.append(
        {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "mode": mode,
            "num_storeys": int(summary["num_storeys"]),
            "span_m": float(summary["span_m"]),
            "design_standard": str(input_snapshot.get("design_standard", "")),
            "total_cost_SGD": float(summary["total_cost_SGD"]),
            "max_utilization": float(summary["max_utilization"]),
            "governing_member_type": summary.get("governing_member_type"),
            "governing_storey": summary.get("governing_storey"),
            "summary": summary,
            "input_snapshot": input_snapshot,
            "excel_path": str(excel_path) if excel_path else None,
            "members": member_rows,
        }
    )

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(runs, f, indent=2)

    return run_id, JSON_PATH
