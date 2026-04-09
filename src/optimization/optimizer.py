from copy import deepcopy
from itertools import product

from src.database.db_query import (
    get_unique_sections_by_shape_sorted,
    get_materials_in_grade_range,
)
from src.models.section import Section
from src.models.material import Material
from src.analysis.analysis_engine import run_analysis


def is_feasible(results, u_min=None, u_max=None):
    for r in results:
        beam_u = r["beam_utilization"]
        col_u = r["column_utilization"]

        if u_min is not None:
            if beam_u < u_min or col_u < u_min:
                return False

        if u_max is not None:
            if beam_u > u_max or col_u > u_max:
                return False

    return True


def satisfies_column_class_rules(candidate, column_class_rules=None):
    if column_class_rules is None:
        return True

    for rule in column_class_rules:
        allowed_classes = rule["allowed_classes"]
        storeys = rule["storeys"]

        for storey in candidate.storeys:
            if storey.level in storeys:
                col_class = storey.column_left.section.section_class
                if col_class not in allowed_classes:
                    return False

    return True


def assign_designs_by_groups(
    candidate,
    beam_group_designs,
    column_group_designs,
    beam_groups,
    column_groups
):
    for group_idx, group_storeys in enumerate(beam_groups):
        section_obj, material_obj = beam_group_designs[group_idx]
        for storey in candidate.storeys:
            if storey.level in group_storeys:
                storey.beam.section = section_obj
                storey.beam.material = material_obj

    for group_idx, group_storeys in enumerate(column_groups):
        section_obj, material_obj = column_group_designs[group_idx]
        for storey in candidate.storeys:
            if storey.level in group_storeys:
                storey.column_left.section = section_obj
                storey.column_right.section = section_obj
                storey.column_left.material = material_obj
                storey.column_right.material = material_obj

    return candidate


def assign_beam_designs_by_groups(candidate, beam_group_designs, beam_groups):
    for group_idx, group_storeys in enumerate(beam_groups):
        section_obj, material_obj = beam_group_designs[group_idx]
        for storey in candidate.storeys:
            if storey.level in group_storeys:
                storey.beam.section = section_obj
                storey.beam.material = material_obj
    return candidate


def assign_column_designs_by_groups(candidate, column_group_designs, column_groups):
    for group_idx, group_storeys in enumerate(column_groups):
        section_obj, material_obj = column_group_designs[group_idx]
        for storey in candidate.storeys:
            if storey.level in group_storeys:
                storey.column_left.section = section_obj
                storey.column_right.section = section_obj
                storey.column_left.material = material_obj
                storey.column_right.material = material_obj
    return candidate


def row_name_set(rows):
    return {r[0] for r in rows}


def add_base_sections_to_pool(rows, base_section_names, shape_filter=None):
    existing = row_name_set(rows)
    extra = []

    for sec in base_section_names:
        row = (sec.name, sec.shape, sec.area, sec.weight, sec.I, sec.W, sec.section_class)
        if shape_filter is not None and sec.shape != shape_filter:
            continue
        if sec.name not in existing:
            extra.append(row)
            existing.add(sec.name)

    return rows + extra


def add_base_materials_to_pool(rows, base_materials):
    existing = {r[0] for r in rows}
    extra = []

    for mat in base_materials:
        row = (mat.grade, mat.fy, mat.cost)
        if mat.grade not in existing:
            extra.append(row)
            existing.add(mat.grade)

    return rows + extra


def build_design_candidates(section_rows, material_rows):
    sections = [Section(*row) for row in section_rows]
    materials = [Material(*row) for row in material_rows]

    design_candidates = []
    for sec in sections:
        for mat in materials:
            design_candidates.append((sec, mat))

    return design_candidates


def estimate_grouped_material_cost(candidate):
    total = 0.0
    for storey in candidate.storeys:
        beam_length = candidate.span
        col_length = storey.height

        total += beam_length * storey.beam.section.weight * storey.beam.material.cost
        total += col_length * storey.column_left.section.weight * storey.column_left.material.cost
        total += col_length * storey.column_right.section.weight * storey.column_right.material.cost

    return total


def run_grouped_optimization(
    base_building,
    design_standard,
    beam_groups,
    column_groups,
    beam_shape="I",
    column_shape="SHS",
    beam_min_grade=235,
    beam_max_grade=355,
    column_min_grade=235,
    column_max_grade=355,
    u_min=None,
    u_max=1.0,
    max_beam_candidates=12,
    max_column_candidates=12,
    column_class_rules=None,
):
    beam_rows = get_unique_sections_by_shape_sorted(beam_shape, sort_by="weight")[:max_beam_candidates]
    column_rows = get_unique_sections_by_shape_sorted(column_shape, sort_by="weight")[:max_column_candidates]

    beam_material_rows = get_materials_in_grade_range(beam_min_grade, beam_max_grade)
    column_material_rows = get_materials_in_grade_range(column_min_grade, column_max_grade)

    base_beam_sections = [storey.beam.section for storey in base_building.storeys]
    base_column_sections = [storey.column_left.section for storey in base_building.storeys]

    base_beam_materials = [storey.beam.material for storey in base_building.storeys]
    base_column_materials = [storey.column_left.material for storey in base_building.storeys]

    beam_rows = add_base_sections_to_pool(beam_rows, base_beam_sections, shape_filter=beam_shape)
    column_rows = add_base_sections_to_pool(column_rows, base_column_sections, shape_filter=column_shape)

    beam_material_rows = add_base_materials_to_pool(beam_material_rows, base_beam_materials)
    column_material_rows = add_base_materials_to_pool(column_material_rows, base_column_materials)

    beam_design_candidates = build_design_candidates(beam_rows, beam_material_rows)
    column_design_candidates = build_design_candidates(column_rows, column_material_rows)

    best_results = None
    best_summary = None
    best_building = None
    best_beam_designs = None
    best_column_designs = None

    beam_group_combos = product(beam_design_candidates, repeat=len(beam_groups))

    combo_count = 0
    feasible_count = 0

    for beam_combo in beam_group_combos:
        beam_base_candidate = deepcopy(base_building)
        beam_base_candidate = assign_beam_designs_by_groups(
            beam_base_candidate,
            beam_group_designs=beam_combo,
            beam_groups=beam_groups
        )

        column_group_combos = product(column_design_candidates, repeat=len(column_groups))

        for column_combo in column_group_combos:
            combo_count += 1

            if combo_count % 500 == 0:
                print(f"[Grouped Opt] Checked {combo_count} combinations... Feasible so far: {feasible_count}")

            candidate = deepcopy(beam_base_candidate)
            candidate = assign_column_designs_by_groups(
                candidate,
                column_group_designs=column_combo,
                column_groups=column_groups
            )

            if not satisfies_column_class_rules(candidate, column_class_rules):
                continue

            estimated_cost = estimate_grouped_material_cost(candidate)
            if best_summary is not None and estimated_cost >= best_summary["total_cost_SGD"]:
                continue

            results, summary = run_analysis(candidate, design_standard)

            if not is_feasible(results, u_min=u_min, u_max=u_max):
                continue

            feasible_count += 1

            if best_summary is None or summary["total_cost_SGD"] < best_summary["total_cost_SGD"]:
                best_results = results
                best_summary = summary
                best_building = candidate
                best_beam_designs = [
                    {"section": sec.name, "grade": mat.grade}
                    for sec, mat in beam_combo
                ]
                best_column_designs = [
                    {"section": sec.name, "grade": mat.grade}
                    for sec, mat in column_combo
                ]

    return {
        "building": best_building,
        "results": best_results,
        "summary": best_summary,
        "best_beam_designs": best_beam_designs,
        "best_column_designs": best_column_designs,
        "best_beam_sections": [d["section"] for d in best_beam_designs] if best_beam_designs else None,
        "best_column_sections": [d["section"] for d in best_column_designs] if best_column_designs else None,
    }


def run_individual_storey_sequential_optimization(
    base_building,
    design_standard,
    beam_shape="I",
    column_shape="SHS",
    u_min=None,
    u_max=1.0,
    max_beam_candidates=12,
    max_column_candidates=12
):
    beam_rows = get_unique_sections_by_shape_sorted(beam_shape, sort_by="weight")[:max_beam_candidates]
    column_rows = get_unique_sections_by_shape_sorted(column_shape, sort_by="weight")[:max_column_candidates]

    base_beam_sections = [storey.beam.section for storey in base_building.storeys]
    base_column_sections = [storey.column_left.section for storey in base_building.storeys]

    beam_rows = add_base_sections_to_pool(beam_rows, base_beam_sections, shape_filter=beam_shape)
    column_rows = add_base_sections_to_pool(column_rows, base_column_sections, shape_filter=column_shape)

    beam_section_objects = [Section(*row) for row in beam_rows]
    column_section_objects = [Section(*row) for row in column_rows]

    candidate = deepcopy(base_building)

    # Optimize beams storey by storey
    for i, storey in enumerate(candidate.storeys):
        best_local_section = storey.beam.section
        best_local_cost = None

        for beam_section in beam_section_objects:
            test_building = deepcopy(candidate)
            test_building.storeys[i].beam.section = beam_section

            results, summary = run_analysis(test_building, design_standard)

            if not is_feasible(results, u_min=u_min, u_max=u_max):
                continue

            if best_local_cost is None or summary["total_cost_SGD"] < best_local_cost:
                best_local_cost = summary["total_cost_SGD"]
                best_local_section = beam_section

        candidate.storeys[i].beam.section = best_local_section

    # Optimize columns storey by storey
    for i, storey in enumerate(candidate.storeys):
        best_local_section = storey.column_left.section
        best_local_cost = None

        for column_section in column_section_objects:
            test_building = deepcopy(candidate)
            test_building.storeys[i].column_left.section = column_section
            test_building.storeys[i].column_right.section = column_section

            results, summary = run_analysis(test_building, design_standard)

            if not is_feasible(results, u_min=u_min, u_max=u_max):
                continue

            if best_local_cost is None or summary["total_cost_SGD"] < best_local_cost:
                best_local_cost = summary["total_cost_SGD"]
                best_local_section = column_section

        candidate.storeys[i].column_left.section = best_local_section
        candidate.storeys[i].column_right.section = best_local_section

    results, summary = run_analysis(candidate, design_standard)

    if not is_feasible(results, u_min=u_min, u_max=u_max):
        return {
            "building": None,
            "results": None,
            "summary": None,
            "best_beam_sections": None,
            "best_column_sections": None
        }

    return {
        "building": candidate,
        "results": results,
        "summary": summary,
        "best_beam_sections": [s.beam.section.name for s in candidate.storeys],
        "best_column_sections": [s.column_left.section.name for s in candidate.storeys]
    }