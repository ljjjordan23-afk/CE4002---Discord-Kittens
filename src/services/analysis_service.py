from src.analysis.analysis_engine import run_analysis


def run_analysis_service(building, design_standard, governing_basis="utilization"):
    results, summary = run_analysis(
        building,
        design_standard,
        governing_basis=governing_basis,
    )
    return {
        "building": building,
        "results": results,
        "summary": summary,
        "mode": "Analysis",
    }
