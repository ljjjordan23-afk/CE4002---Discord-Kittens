from pathlib import Path
import sys
import pandas as pd
import os
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))


def get_deflection_limit_ratio(design_standard):
    """
    Returns denominator n in allowable deflection = L / n.

    This is a simplified project mapping for generic storey beams.
    It is not a full substitute for detailed code-specific serviceability rules.
    """
    code = str(getattr(design_standard, "code", design_standard)).strip().upper()

    mapping = {
        "EUROCODE": 360.0,
        "ASCE": 360.0,
        "BS": 360.0,
        "CSA": 360.0,
        "CN": 250.0,
    }

    return mapping.get(code, 360.0)

print("RUN_ANALYSIS IS EXECUTING")
def get_deflection_limit_mm(span_m, design_standard):
    ratio = get_deflection_limit_ratio(design_standard)
    return span_m * 1000.0 / ratio

def run_analysis(building, design_standard, governing_basis="utilization"):
    results = []
    total_cost = 0.0

    # First compute each storey's design load and column share
    storey_data = []
    for storey in building.storeys:
        w = storey.design_load(design_standard)          # kN/m
        beam_force_to_columns = w * building.span / 2    # kN to each column from this storey

        storey_data.append({
            "storey": storey,
            "w": w,
            "beam_force_to_columns": beam_force_to_columns
        })

    # Accumulate column force from top to bottom
    accumulated_column_force = 0.0
    for item in reversed(storey_data):
        accumulated_column_force += item["beam_force_to_columns"]
        item["column_force"] = accumulated_column_force

    # Governing trackers
    max_utilization_value = -1.0
    max_utilization_member_type = None
    max_utilization_storey = None

    max_stress_value = -1.0
    max_stress_member_type = None
    max_stress_storey = None

    max_moment_value = -1.0
    max_moment_member_type = "Beam"
    max_moment_storey = None

    max_deflection_value = -1.0
    max_deflection_member_type = "Beam"
    max_deflection_storey = None

    # Run calculations in normal storey order
    for item in storey_data:
        storey = item["storey"]
        w = item["w"]
        P = item["column_force"]

        beam = storey.beam
        col_left = storey.column_left
        col_right = storey.column_right

        beam_moment = beam.max_moment(w, building.span)
        beam_stress = beam.max_stress(w, building.span)
        beam_util = beam.utilization(w, building.span)
        beam_deflection = beam.max_deflection(w, building.span)

        beam_deflection_limit_mm = get_deflection_limit_mm(building.span, design_standard)
        beam_deflection_ok = beam_deflection <= beam_deflection_limit_mm
        beam_deflection_ratio_used = get_deflection_limit_ratio(design_standard)
        beam_deflection_utilization = (
            beam_deflection / beam_deflection_limit_mm
            if beam_deflection_limit_mm > 0 else 0.0
        )

        beam_cost = beam.cost()

        col_stress = col_left.max_stress(P)
        col_axial_util = col_left.axial_utilization(P)

        # simple default effective length factor
        column_K = 1.0
        col_buckling_capacity_kN = col_left.buckling_capacity(storey.height, K=column_K)
        col_buckling_util = col_left.buckling_utilization(P, storey.height, K=column_K)

        col_util = max(col_axial_util, col_buckling_util)
        col_governing_check = "Buckling" if col_buckling_util >= col_axial_util else "Axial stress"
        col_left_cost = col_left.cost()
        col_right_cost = col_right.cost()

        storey_total_cost = beam_cost + col_left_cost + col_right_cost
        total_cost += storey_total_cost

        # Track max utilization
        if beam_util > max_utilization_value:
            max_utilization_value = beam_util
            max_utilization_member_type = "Beam"
            max_utilization_storey = storey.level

        if col_util > max_utilization_value:
            max_utilization_value = col_util
            max_utilization_member_type = "Column"
            max_utilization_storey = storey.level

        # Track max stress
        if beam_stress > max_stress_value:
            max_stress_value = beam_stress
            max_stress_member_type = "Beam"
            max_stress_storey = storey.level

        if col_stress > max_stress_value:
            max_stress_value = col_stress
            max_stress_member_type = "Column"
            max_stress_storey = storey.level

        # Track max moment (beam only)
        if beam_moment > max_moment_value:
            max_moment_value = beam_moment
            max_moment_storey = storey.level

        # Track max deflection (beam only)
        if beam_deflection > max_deflection_value:
            max_deflection_value = beam_deflection
            max_deflection_storey = storey.level
        print(
            "DEBUG COLUMN:",
            {
                "storey": storey.level,
                "section": col_left.section.name,
                "area": col_left.section.area,
                "I": col_left.section.I,
                "P": P,
                "col_stress": col_stress,
                "col_axial_util": col_axial_util,
                "col_buckling_capacity_kN": col_buckling_capacity_kN,
                "col_buckling_util": col_buckling_util,
            }
        )
        results.append({
            "storey": storey.level,
            "height_m": storey.height,
            "dead_load_kN_per_m": storey.dead_load,
            "live_load_kN_per_m": storey.live_load,
            "design_load_kN_per_m": w,

            "beam_section": beam.section.name,
            "beam_grade": beam.material.grade,
            "beam_Mmax_kNm": beam_moment,
            "beam_stress_MPa": beam_stress,
            "beam_utilization": beam_util,
            "beam_deflection_mm": beam_deflection,
            "beam_deflection_limit_mm": beam_deflection_limit_mm,
            "beam_deflection_ratio_used": beam_deflection_ratio_used,
            "beam_deflection_utilization": beam_deflection_utilization,
            "beam_deflection_ok": beam_deflection_ok,
            "beam_cost_SGD": beam_cost,

            "column_section": col_left.section.name,
            "column_grade": col_left.material.grade,
            "column_force_kN": P,
            "column_stress_MPa": col_stress,
            "column_utilization": col_util,
            "column_axial_utilization": col_axial_util,
            "column_buckling_capacity_kN": col_buckling_capacity_kN,
            "column_buckling_utilization": col_buckling_util,
            "column_governing_check": col_governing_check,
            "column_left_cost_SGD": col_left_cost,
            "column_right_cost_SGD": col_right_cost,

            "storey_total_cost_SGD": storey_total_cost
        })

    # Select governing output based on user choice
    governing_basis = str(governing_basis).strip().lower()

    if governing_basis == "stress":
        governing_member_type = max_stress_member_type
        governing_storey = max_stress_storey
        governing_value = max_stress_value
        governing_label = "Max Stress"
        governing_unit = "MPa"

    elif governing_basis == "moment":
        governing_member_type = "Beam"
        governing_storey = max_moment_storey
        governing_value = max_moment_value
        governing_label = "Max Moment"
        governing_unit = "kN·m"

    elif governing_basis == "deflection":
        governing_member_type = "Beam"
        governing_storey = max_deflection_storey
        governing_value = max_deflection_value
        governing_label = "Max Deflection"
        governing_unit = "mm"

    else:
        governing_member_type = max_utilization_member_type
        governing_storey = max_utilization_storey
        governing_value = max_utilization_value
        governing_label = "Max Utilization"
        governing_unit = "-"

    summary = {
        "num_storeys": building.num_storeys,
        "span_m": building.span,
        "total_cost_SGD": total_cost,

        "governing_basis": governing_basis,
        "governing_label": governing_label,
        "governing_unit": governing_unit,
        "governing_member_type": governing_member_type,
        "governing_storey": governing_storey,
        "governing_value": governing_value,

        "max_utilization": max_utilization_value,
        "max_utilization_member_type": max_utilization_member_type,
        "max_utilization_storey": max_utilization_storey,

        "max_stress_MPa": max_stress_value,
        "max_stress_member_type": max_stress_member_type,
        "max_stress_storey": max_stress_storey,

        "max_moment_kNm": max_moment_value,
        "max_moment_storey": max_moment_storey,

        "max_deflection_mm": max_deflection_value,
        "max_deflection_storey": max_deflection_storey,
    }

    return results, summary

def export_results_to_excel(results, summary, filename=None):
    """
    Export the current optimized solution to Excel.
    If filename is not provided, create a timestamped one.
    """
    os.makedirs("outputs", exist_ok=True)

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"outputs/optimized_solution_{timestamp}.xlsx"

    df = pd.DataFrame(results)

    columns_order = [
        "storey",
        "height_m",
        "dead_load_kN_per_m",
        "live_load_kN_per_m",
        "design_load_kN_per_m",

        "beam_section",
        "beam_grade",
        "beam_Mmax_kNm",
        "beam_stress_MPa",
        "beam_utilization",
        "beam_deflection_mm",
        "beam_cost_SGD",

        "column_section",
        "column_grade",
        "column_force_kN",
        "column_stress_MPa",
        "column_utilization",
        "column_axial_utilization",
        "column_buckling_capacity_kN",
        "column_buckling_utilization",
        "column_governing_check",
        "column_left_cost_SGD",
        "column_right_cost_SGD",

        "storey_total_cost_SGD",
    ]

    columns_order = [col for col in columns_order if col in df.columns]
    df = df[columns_order]

    summary_df = pd.DataFrame([summary])

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Optimized Solution", index=False)
        summary_df.to_excel(writer, sheet_name="Summary", index=False)

    return filename
