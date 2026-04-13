from __future__ import annotations

from copy import deepcopy
from itertools import product
from typing import Iterable, List, Dict, Tuple, Optional, Sequence, Set

from src.database.db_query import (
    get_unique_sections_by_shape_sorted,
    get_materials_in_grade_range,
)
from src.models.section import Section
from src.models.material import Material
from src.analysis.analysis_engine import run_analysis


# ============================================================
# Helpers: validation / normalization
# ============================================================

VALID_SHAPES = {"I", "SHS", "CHS"}


def _as_shape_list(shapes) -> List[str]:
    """
    Accepts:
      - "I"
      - ["SHS", "CHS"]
      - ("I", "SHS")
      - None
    Returns a validated list of shapes.
    """
    if shapes is None:
        return []

    if isinstance(shapes, str):
        shapes = [shapes]

    out = []
    for s in shapes:
        s = str(s).strip().upper()
        if s not in VALID_SHAPES:
            raise ValueError(
                f"Invalid section shape '{s}'. Allowed shapes are {sorted(VALID_SHAPES)}."
            )
        if s not in out:
            out.append(s)
    return out


def _sorted_unique_ints(values: Iterable[int]) -> List[int]:
    return sorted({int(v) for v in values})


def normalize_groups(groups: Optional[Sequence[Sequence[int]]], n_storeys: int) -> List[List[int]]:
    """
    Validates user-defined groups.
    Rules:
    - every storey from 1..n must appear exactly once
    - no duplicates
    - no missing storeys
    - no out-of-range storeys
    """
    if not groups:
        return [[i] for i in range(1, n_storeys + 1)]

    normalized: List[List[int]] = []
    seen: List[int] = []

    for g in groups:
        if not g:
            raise ValueError("A group cannot be empty.")

        group = _sorted_unique_ints(g)

        for s in group:
            if s < 1 or s > n_storeys:
                raise ValueError(
                    f"Storey {s} is out of range. Valid storeys are 1 to {n_storeys}."
                )

        normalized.append(group)
        seen.extend(group)

    seen_sorted = sorted(seen)

    if len(seen_sorted) != len(set(seen_sorted)):
        duplicates = sorted({x for x in seen_sorted if seen_sorted.count(x) > 1})
        raise ValueError(f"Duplicate storeys detected in groups: {duplicates}")

    expected = list(range(1, n_storeys + 1))
    if seen_sorted != expected:
        missing = sorted(set(expected) - set(seen_sorted))
        extra = sorted(set(seen_sorted) - set(expected))
        msg = []
        if missing:
            msg.append(f"missing storeys {missing}")
        if extra:
            msg.append(f"invalid storeys {extra}")
        raise ValueError("Groups must cover every storey exactly once: " + ", ".join(msg))

    return normalized


def normalize_column_class_rules(
    column_class_rules: Optional[List[Dict]],
    n_storeys: int
) -> List[Dict]:
    """
    Expected input format:
    [
        {
            "storeys": [1, 2, 3],
            "allowed_classes": [1, 2]
        },
        ...
    ]
    """
    if not column_class_rules:
        return []

    out = []
    for idx, rule in enumerate(column_class_rules, start=1):
        if "storeys" not in rule or "allowed_classes" not in rule:
            raise ValueError(
                f"Column class rule #{idx} must contain 'storeys' and 'allowed_classes'."
            )

        storeys = _sorted_unique_ints(rule["storeys"])
        allowed_classes = _sorted_unique_ints(rule["allowed_classes"])

        for s in storeys:
            if s < 1 or s > n_storeys:
                raise ValueError(
                    f"Column class rule #{idx} has out-of-range storey {s}. "
                    f"Valid storeys are 1 to {n_storeys}."
                )

        for c in allowed_classes:
            if c not in {1, 2, 3, 4}:
                raise ValueError(
                    f"Column class rule #{idx} has invalid class {c}. Allowed classes are 1, 2, 3, 4."
                )

        out.append({"storeys": storeys, "allowed_classes": allowed_classes})

    return out


# ============================================================
# Helpers: feasibility / candidate handling
# ============================================================

def is_feasible(results, u_min=None, u_max=None) -> bool:
    for r in results:
        beam_u = r["beam_utilization"]
        col_u = r["column_utilization"]

        if u_min is not None and (beam_u < u_min or col_u < u_min):
            return False

        if u_max is not None and (beam_u > u_max or col_u > u_max):
            return False

    return True


def satisfies_column_class_rules(candidate, column_class_rules=None) -> bool:
    if not column_class_rules:
        return True

    for rule in column_class_rules:
        allowed_classes = set(rule["allowed_classes"])
        storeys = set(rule["storeys"])

        for storey in candidate.storeys:
            if storey.level in storeys:
                col_class = storey.column_left.section.section_class
                if col_class not in allowed_classes:
                    return False

    return True


def row_name_set(rows):
    return {r[0] for r in rows}


def add_base_sections_to_pool(rows, base_section_names, allowed_shapes=None):
    existing = row_name_set(rows)
    extra = []
    allowed_shapes = set(_as_shape_list(allowed_shapes)) if allowed_shapes else None

    for sec in base_section_names:
        row = (sec.name, sec.shape, sec.area, sec.weight, sec.I, sec.W, sec.section_class)
        if allowed_shapes is not None and sec.shape not in allowed_shapes:
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


def get_section_rows_for_shapes(
    shapes,
    sort_by="weight",
    max_candidates_per_shape=12
):
    """
    Returns a combined candidate pool across one or more allowed shapes.
    Keeps up to max_candidates_per_shape from each shape to prevent one shape
    from dominating the pool.
    """
    shapes = _as_shape_list(shapes)
    all_rows = []
    seen_names = set()

    for shape in shapes:
        rows = get_unique_sections_by_shape_sorted(shape, sort_by=sort_by)[:max_candidates_per_shape]
        for row in rows:
            if row[0] not in seen_names:
                all_rows.append(row)
                seen_names.add(row[0])

    # Final lightweight sorting by weight if that field exists in row[3]
    all_rows.sort(key=lambda r: r[3])
    return all_rows


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


def estimate_grouped_material_cost(candidate) -> float:
    total = 0.0
    for storey in candidate.storeys:
        beam_length = candidate.span
        col_length = storey.height

        total += beam_length * storey.beam.section.weight * storey.beam.material.cost
        total += col_length * storey.column_left.section.weight * storey.column_left.material.cost
        total += col_length * storey.column_right.section.weight * storey.column_right.material.cost

    return total


# ============================================================
# Main optimizer: grouped exact search over filtered candidate pool
# ============================================================

def run_grouped_optimization(
    base_building,
    design_standard,
    beam_groups=None,
    column_groups=None,
    beam_shapes=("I",),
    column_shapes=("SHS",),
    beam_min_grade=235,
    beam_max_grade=355,
    column_min_grade=235,
    column_max_grade=355,
    u_min=None,
    u_max=1.0,
    max_beam_candidates_per_shape=12,
    max_column_candidates_per_shape=12,
    column_class_rules=None,
    verbose=False,
):
    """
    Strongest Module 2 optimizer in this file.

    It searches all combinations across:
    - grouped beam section+grade choices
    - grouped column section+grade choices
    subject to:
    - utilization range
    - beam and column allowed shapes
    - beam and column grade ranges
    - grouped storey assignments
    - column section class rules

    Note:
    This finds the best feasible design within the filtered candidate pools,
    not necessarily across the entire full database if candidate caps are used.
    """
    n_storeys = len(base_building.storeys)

    beam_groups = normalize_groups(beam_groups, n_storeys)
    column_groups = normalize_groups(column_groups, n_storeys)
    beam_shapes = _as_shape_list(beam_shapes)
    column_shapes = _as_shape_list(column_shapes)
    column_class_rules = normalize_column_class_rules(column_class_rules, n_storeys)

    beam_rows = get_section_rows_for_shapes(
        beam_shapes,
        sort_by="weight",
        max_candidates_per_shape=max_beam_candidates_per_shape
    )
    column_rows = get_section_rows_for_shapes(
        column_shapes,
        sort_by="weight",
        max_candidates_per_shape=max_column_candidates_per_shape
    )

    beam_material_rows = get_materials_in_grade_range(beam_min_grade, beam_max_grade)
    column_material_rows = get_materials_in_grade_range(column_min_grade, column_max_grade)

    base_beam_sections = [storey.beam.section for storey in base_building.storeys]
    base_column_sections = [storey.column_left.section for storey in base_building.storeys]
    base_beam_materials = [storey.beam.material for storey in base_building.storeys]
    base_column_materials = [storey.column_left.material for storey in base_building.storeys]

    beam_rows = add_base_sections_to_pool(beam_rows, base_beam_sections, allowed_shapes=beam_shapes)
    column_rows = add_base_sections_to_pool(column_rows, base_column_sections, allowed_shapes=column_shapes)
    beam_material_rows = add_base_materials_to_pool(beam_material_rows, base_beam_materials)
    column_material_rows = add_base_materials_to_pool(column_material_rows, base_column_materials)

    beam_design_candidates = build_design_candidates(beam_rows, beam_material_rows)
    column_design_candidates = build_design_candidates(column_rows, column_material_rows)

    if not beam_design_candidates:
        raise ValueError("No beam design candidates found after applying shape and grade filters.")
    if not column_design_candidates:
        raise ValueError("No column design candidates found after applying shape and grade filters.")

    best_results = None
    best_summary = None
    best_building = None
    best_beam_designs = None
    best_column_designs = None

    combo_count = 0
    feasible_count = 0

    beam_group_combos = product(beam_design_candidates, repeat=len(beam_groups))

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
                best_beam_designs = [{"section": sec.name, "grade": mat.grade} for sec, mat in beam_combo]
                best_column_designs = [{"section": sec.name, "grade": mat.grade} for sec, mat in column_combo]

            if verbose and combo_count % 500 == 0:
                print(
                    f"[Grouped Opt] Checked {combo_count} combinations | "
                    f"Feasible {feasible_count} | "
                    f"Best cost: {best_summary['total_cost_SGD'] if best_summary else 'N/A'}"
                )

    if best_building is None:
        return {
            "building": None,
            "results": None,
            "summary": None,
            "best_beam_designs": None,
            "best_column_designs": None,
            "best_beam_sections": None,
            "best_column_sections": None,
            "meta": {
                "checked_combinations": combo_count,
                "feasible_combinations": feasible_count,
            }
        }

    return {
        "building": best_building,
        "results": best_results,
        "summary": best_summary,
        "best_beam_designs": best_beam_designs,
        "best_column_designs": best_column_designs,
        "best_beam_sections": [d["section"] for d in best_beam_designs],
        "best_column_sections": [d["section"] for d in best_column_designs],
        "meta": {
            "checked_combinations": combo_count,
            "feasible_combinations": feasible_count,
        }
    }


# ============================================================
# Faster fallback: storeywise greedy search including grades
# ============================================================

def run_storeywise_greedy_optimization(
    base_building,
    design_standard,
    beam_shapes=("I",),
    column_shapes=("SHS",),
    beam_min_grade=235,
    beam_max_grade=355,
    column_min_grade=235,
    column_max_grade=355,
    u_min=None,
    u_max=1.0,
    max_beam_candidates_per_shape=12,
    max_column_candidates_per_shape=12,
    column_class_rules=None,
):
    """
    Faster fallback optimizer.

    Improvements over old sequential optimizer:
    - considers section + steel grade, not section only
    - supports multiple allowed shapes
    - supports column class rules

    Still greedy, so it is not guaranteed to find the global best design.
    """
    n_storeys = len(base_building.storeys)
    column_class_rules = normalize_column_class_rules(column_class_rules, n_storeys)

    beam_shapes = _as_shape_list(beam_shapes)
    column_shapes = _as_shape_list(column_shapes)

    beam_rows = get_section_rows_for_shapes(
        beam_shapes,
        sort_by="weight",
        max_candidates_per_shape=max_beam_candidates_per_shape
    )
    column_rows = get_section_rows_for_shapes(
        column_shapes,
        sort_by="weight",
        max_candidates_per_shape=max_column_candidates_per_shape
    )

    beam_material_rows = get_materials_in_grade_range(beam_min_grade, beam_max_grade)
    column_material_rows = get_materials_in_grade_range(column_min_grade, column_max_grade)

    base_beam_sections = [storey.beam.section for storey in base_building.storeys]
    base_column_sections = [storey.column_left.section for storey in base_building.storeys]
    base_beam_materials = [storey.beam.material for storey in base_building.storeys]
    base_column_materials = [storey.column_left.material for storey in base_building.storeys]

    beam_rows = add_base_sections_to_pool(beam_rows, base_beam_sections, allowed_shapes=beam_shapes)
    column_rows = add_base_sections_to_pool(column_rows, base_column_sections, allowed_shapes=column_shapes)
    beam_material_rows = add_base_materials_to_pool(beam_material_rows, base_beam_materials)
    column_material_rows = add_base_materials_to_pool(column_material_rows, base_column_materials)

    beam_design_candidates = build_design_candidates(beam_rows, beam_material_rows)
    column_design_candidates = build_design_candidates(column_rows, column_material_rows)

    if not beam_design_candidates:
        raise ValueError("No beam design candidates found after applying filters.")
    if not column_design_candidates:
        raise ValueError("No column design candidates found after applying filters.")

    candidate = deepcopy(base_building)

    # ---- Optimize beams storey by storey
    for i, storey in enumerate(candidate.storeys):
        best_local_design = (storey.beam.section, storey.beam.material)
        best_local_cost = None

        for beam_section, beam_material in beam_design_candidates:
            test_building = deepcopy(candidate)
            test_building.storeys[i].beam.section = beam_section
            test_building.storeys[i].beam.material = beam_material

            if not satisfies_column_class_rules(test_building, column_class_rules):
                continue

            results, summary = run_analysis(test_building, design_standard)

            if not is_feasible(results, u_min=u_min, u_max=u_max):
                continue

            if best_local_cost is None or summary["total_cost_SGD"] < best_local_cost:
                best_local_cost = summary["total_cost_SGD"]
                best_local_design = (beam_section, beam_material)

        candidate.storeys[i].beam.section = best_local_design[0]
        candidate.storeys[i].beam.material = best_local_design[1]

    # ---- Optimize columns storey by storey
    for i, storey in enumerate(candidate.storeys):
        best_local_design = (storey.column_left.section, storey.column_left.material)
        best_local_cost = None

        for column_section, column_material in column_design_candidates:
            test_building = deepcopy(candidate)
            test_building.storeys[i].column_left.section = column_section
            test_building.storeys[i].column_right.section = column_section
            test_building.storeys[i].column_left.material = column_material
            test_building.storeys[i].column_right.material = column_material

            if not satisfies_column_class_rules(test_building, column_class_rules):
                continue

            results, summary = run_analysis(test_building, design_standard)

            if not is_feasible(results, u_min=u_min, u_max=u_max):
                continue

            if best_local_cost is None or summary["total_cost_SGD"] < best_local_cost:
                best_local_cost = summary["total_cost_SGD"]
                best_local_design = (column_section, column_material)

        candidate.storeys[i].column_left.section = best_local_design[0]
        candidate.storeys[i].column_right.section = best_local_design[0]
        candidate.storeys[i].column_left.material = best_local_design[1]
        candidate.storeys[i].column_right.material = best_local_design[1]

    results, summary = run_analysis(candidate, design_standard)

    if not satisfies_column_class_rules(candidate, column_class_rules):
        return {
            "building": None,
            "results": None,
            "summary": None,
            "best_beam_designs": None,
            "best_column_designs": None,
            "best_beam_sections": None,
            "best_column_sections": None
        }

    if not is_feasible(results, u_min=u_min, u_max=u_max):
        return {
            "building": None,
            "results": None,
            "summary": None,
            "best_beam_designs": None,
            "best_column_designs": None,
            "best_beam_sections": None,
            "best_column_sections": None
        }

    return {
        "building": candidate,
        "results": results,
        "summary": summary,
        "best_beam_designs": [
            {"section": s.beam.section.name, "grade": s.beam.material.grade}
            for s in candidate.storeys
        ],
        "best_column_designs": [
            {"section": s.column_left.section.name, "grade": s.column_left.material.grade}
            for s in candidate.storeys
        ],
        "best_beam_sections": [s.beam.section.name for s in candidate.storeys],
        "best_column_sections": [s.column_left.section.name for s in candidate.storeys]
    }


# ============================================================
# Backward-compatible wrapper
# ============================================================

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
    """
    Kept for backward compatibility with older UI code.

    Internally redirects to the upgraded greedy optimizer.
    """
    return run_storeywise_greedy_optimization(
        base_building=base_building,
        design_standard=design_standard,
        beam_shapes=[beam_shape],
        column_shapes=[column_shape],
        u_min=u_min,
        u_max=u_max,
        max_beam_candidates_per_shape=max_beam_candidates,
        max_column_candidates_per_shape=max_column_candidates,
    )