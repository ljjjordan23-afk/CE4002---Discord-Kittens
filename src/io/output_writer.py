import pandas as pd
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "outputs"


def write_analysis_results(results, summary, filename="module1_results.xlsx"):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = OUTPUT_DIR / filename

    results_df = pd.DataFrame(results)
    summary_df = pd.DataFrame([summary])

    # Sort nicely
    if "storey" in results_df.columns:
        results_df = results_df.sort_values("storey").reset_index(drop=True)

    # Round numeric columns for nicer output
    results_df = results_df.round(3)
    summary_df = summary_df.round(3)

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        results_df.to_excel(writer, sheet_name="Member Results", index=False)
        summary_df.to_excel(writer, sheet_name="Summary", index=False)

    return filepath