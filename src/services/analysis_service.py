from src.analysis.analysis_engine import run_analysis


def run_analysis_service(
    building,
    design_standard,
    governing_basis="utilization",
    include_column_buckling=False,
    column_buckling_K=1.0,
):
    results, summary = run_analysis(
        building,
        design_standard,
        governing_basis=governing_basis,
        include_column_buckling=include_column_buckling,
        column_buckling_K=column_buckling_K,
    )
    return {
        "building": building,
        "results": results,
        "summary": summary,
        "mode": "Analysis",
    }