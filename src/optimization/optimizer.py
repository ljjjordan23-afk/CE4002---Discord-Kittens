from copy import deepcopy
from dataclasses import dataclass
from math import prod

from pyparsing import col

from src.analysis.analysis_engine import get_deflection_limit_mm, run_analysis
from src.database.db_query import (
    get_materials_in_grade_range,
    get_unique_sections_by_shape_sorted,
)
from src.io.output_writer import write_optimization_results
from src.database.optimization_results_db import save_optimization_run
from src.models.material import Material
from src.models.section import Section


@dataclass
class CandidateDesign:
    member_type: str
    group_storeys: list
    section_name: str
    grade: str
    total_cost: float
    min_utilization: float
    max_utilization: float
    shape: str
    section_class: int
    details: list


def individual_storey_groups(num_storeys):
    return [[storey] for storey in range(1, int(num_storeys) + 1)]


def _normalize_groups(groups, num_storeys):
    normalized = []
    expected = set(range(1, int(num_storeys) + 1))
    seen = set()

    for group in groups:
        cleaned = sorted({int(storey) for storey in group})
        if not cleaned:
            raise ValueError("Empty optimization group is not allowed.")

        invalid = [storey for storey in cleaned if storey not in expected]
        if invalid:
            raise ValueError(f"Invalid storey numbers in optimization group: {invalid}")

        overlap = seen.intersection(cleaned)
        if overlap:
            raise ValueError(f"Overlapping optimization group storeys detected: {sorted(overlap)}")

        normalized.append(cleaned)
        seen.update(cleaned)

    if seen != expected:
        missing = sorted(expected - seen)
        raise ValueError(f"Optimization groups must cover every storey exactly once. Missing: {missing}")

    return normalized


def _allowed_classes_for_storey(storey, class_rules):
    if not class_rules:
        return None

    allowed = set()
    for rule in class_rules:
        rule_storeys = {int(s) for s in rule.get("storeys", [])}
        if int(storey) in rule_storeys:
            allowed.update(int(c) for c in rule.get("allowed_classes", []))

    if not allowed:
        return None

    return allowed


def _get_sections_for_shapes(shapes, max_per_shape=None):
    sections = []
    seen_names = set()

    for shape in shapes:
        rows = get_unique_sections_by_shape_sorted(shape, sort_by="weight")

        if max_per_shape is not None and max_per_shape > 0:
            rows = rows[:max_per_shape]
        for row in rows:
            if row[0] in seen_names:
                continue
            seen_names.add(row[0])
            sections.append(Section(*row))

    sections.sort(key=lambda s: (s.weight, s.area, s.name))
    return sections


def _get_materials(min_grade, max_grade):
    return [Material(*row) for row in get_materials_in_grade_range(f"S{min_grade}", f"S{max_grade}")]


def _prepare_storey_data(building, design_standard):
    prepared = []
    accumulated_column_force = 0.0

    temp = []
    for storey in building.storeys:
        design_load = storey.design_load(design_standard)
        beam_force_to_columns = design_load * building.span / 2.0
        temp.append(
            {
                "storey": storey.level,
                "height_m": storey.height,
                "design_load_kN_per_m": design_load,
                "beam_force_to_columns": beam_force_to_columns,
            }
        )

    for item in reversed(temp):
        accumulated_column_force += item["beam_force_to_columns"]
        item["column_force_kN"] = accumulated_column_force

    prepared.extend(sorted(temp, key=lambda row: row["storey"]))
    return prepared


def _evaluate_beam_group(
    building,
    design_standard,
    group_storeys,
    sections,
    materials,
    u_min,
    u_max,
    class_rules,
):
    candidates = []
    span = building.span

    for section in sections:
        class_ok = True
        for storey in group_storeys:
            allowed_classes = _allowed_classes_for_storey(storey, class_rules)
            if allowed_classes is not None and int(section.section_class) not in allowed_classes:
                class_ok = False
                break
        if not class_ok:
            continue

        for material in materials:
            details = []
            feasible = True

            for storey_idx in group_storeys:
                storey = building.storeys[storey_idx - 1]
                beam = deepcopy(storey.beam)
                beam.section = section
                beam.material = material

                utilization = beam.utilization(storey.design_load(design_standard), span)
                deflection_mm = beam.max_deflection(storey.design_load(design_standard), span)
                deflection_limit_mm = get_deflection_limit_mm(span, design_standard)

                if utilization < u_min or utilization > u_max or deflection_mm > deflection_limit_mm:
                    feasible = False
                    break

                details.append(
                    {
                        "storey": storey_idx,
                        "utilization": utilization,
                        "deflection_mm": deflection_mm,
                        "cost_SGD": beam.cost(),
                    }
                )

            if not feasible:
                continue

            candidates.append(
                CandidateDesign(
                    member_type="Beam",
                    group_storeys=group_storeys,
                    section_name=section.name,
                    grade=material.grade,
                    total_cost=sum(item["cost_SGD"] for item in details),
                    min_utilization=min(item["utilization"] for item in details),
                    max_utilization=max(item["utilization"] for item in details),
                    shape=section.shape,
                    section_class=int(section.section_class),
                    details=details,
                )
            )
    print(f"DEBUG: Beam group {group_storeys} - evaluated {len(sections)} sections, {len(materials)} materials, generated {len(candidates)} candidates")
    if candidates:
        print(f"DEBUG: Cheapest beam candidate: {candidates[0].section_name} {candidates[0].grade} cost={candidates[0].total_cost}")

    candidates.sort(
        key=lambda c: (
            c.total_cost,
            abs(((u_min + u_max) / 2.0) - c.max_utilization),
            c.section_name,
            c.grade,
        )
    )
    return candidates


def _evaluate_column_group(
    building,
    design_standard,
    group_storeys,
    sections,
    materials,
    u_min,
    u_max,
    class_rules,
    include_column_buckling=False,
    column_k=1.0,
):
    candidates = []
    storey_lookup = {item["storey"]: item for item in _prepare_storey_data(building, design_standard)}
    
    class_rejected = 0
    util_rejected = 0
    sample_utils = []
    min_util_achieved = float('inf')
    best_section_for_min_util = None
    
    # Governing storey: the one with HIGHEST load (lowest storey number = highest cumulative force)
    governing_storey_idx = min(group_storeys)  # Storey 1 carries more than storey 2, etc.
    governing_force_kN = storey_lookup[governing_storey_idx]["column_force_kN"]
    governing_storey_height = building.storeys[governing_storey_idx - 1].height
    
    # Sort sections by area ascending (smallest first for economy)
    sorted_sections = sorted(sections, key=lambda s: (s.area, s.weight))
    # Sort materials by strength ascending (lowest grade first for cost, highest grade last for performance)
    sorted_materials = sorted(materials, key=lambda m: m.fy)

    for section in sorted_sections:
        class_ok = True
        for storey in group_storeys:
            allowed_classes = _allowed_classes_for_storey(storey, class_rules)
            if allowed_classes is not None and int(section.section_class) not in allowed_classes:
                class_ok = False
                break
        if not class_ok:
            class_rejected += 1
            continue

        # For each section, try materials from lowest to highest strength
        for material in sorted_materials:
            # Check all storeys in the group for utilization bounds
            details = []
            max_util = 0.0
            min_util = float('inf')
            for storey_idx in group_storeys:
                storey = building.storeys[storey_idx - 1]
                col = deepcopy(storey.column_left)
                col.section = section
                col.material = material

                force_kN = storey_lookup[storey_idx]["column_force_kN"]
                if include_column_buckling:
                    util = col.governing_utilization(force_kN, storey.height, K=column_k)
                else:
                    util = col.axial_utilization(force_kN)
                max_util = max(max_util, util)
                min_util = min(min_util, util)

                details.append(
                    {
                        "storey": storey_idx,
                        "utilization": util,
                        "cost_SGD": col.cost() * 2.0,
                    }
                )

            # Track minimum utilization found across all attempts
            if min_util < min_util_achieved:
                min_util_achieved = min_util
                best_section_for_min_util = (section.name, material.grade, min_util)
            
            if len(sample_utils) < 3:
                sample_utils.append((section.name, material.grade, governing_storey_idx, f"util={max_util:.2f}"))

            # Reject if any storey exceeds upper bound or any below lower bound
            if max_util > u_max or min_util < u_min:
                util_rejected += 1
                continue

            candidates.append(
                CandidateDesign(
                    member_type="Column",
                    group_storeys=group_storeys,
                    section_name=section.name,
                    grade=material.grade,
                    total_cost=sum(item["cost_SGD"] for item in details),
                    min_utilization=min(item["utilization"] for item in details),
                    max_utilization=max(item["utilization"] for item in details),
                    shape=section.shape,
                    section_class=int(section.section_class),
                    details=details,
                )
            )

    candidates.sort(
        key=lambda c: (
            c.total_cost,
            abs(((u_min + u_max) / 2.0) - c.max_utilization),
            c.section_name,
            c.grade,
        )
    )
    
    # Debug: show what was evaluated
    min_section_tried = sorted_sections[0].name if sorted_sections else "N/A"
    max_section_tried = sorted_sections[-1].name if sorted_sections else "N/A"
    
    print(f"DEBUG: Column group {group_storeys} - evaluated {len(sorted_sections)} sections, {len(sorted_materials)} materials, generated {len(candidates)} candidates")
    if candidates:
        print(f"DEBUG: Cheapest column candidate: {candidates[0].section_name} {candidates[0].grade} cost={candidates[0].total_cost}")
    if class_rejected > 0:
        print(f"DEBUG: {class_rejected} sections rejected by class rules, {util_rejected} by utilization bounds")
    if sample_utils:
        print(f"DEBUG: Sample utils: {sample_utils}")
    return candidates


def _apply_designs_to_building(base_building, beam_designs, beam_groups, column_designs, column_groups):
    building = deepcopy(base_building)

    for group, design in zip(beam_groups, beam_designs):
        for storey_idx in group:
            storey = building.storeys[storey_idx - 1]
            storey.beam.section = design["section"]
            storey.beam.material = design["material"]

    for group, design in zip(column_groups, column_designs):
        for storey_idx in group:
            storey = building.storeys[storey_idx - 1]
            storey.column_left.section = design["section"]
            storey.column_left.material = design["material"]
            storey.column_right.section = design["section"]
            storey.column_right.material = design["material"]

    return building


def _candidate_to_design(candidate, sections_by_name, materials_by_grade):
    return {
        "section": sections_by_name[candidate.section_name],
        "material": materials_by_grade[candidate.grade],
    }


def _serialize_group_designs(candidates):
    serialized = []
    for candidate in candidates:
        serialized.append(
            {
                "storeys": candidate.group_storeys,
                "section": candidate.section_name,
                "grade": candidate.grade,
                "shape": candidate.shape,
                "section_class": candidate.section_class,
                "total_cost_SGD": round(candidate.total_cost, 3),
                "min_utilization": round(candidate.min_utilization, 3),
                "max_utilization": round(candidate.max_utilization, 3),
            }
        )
    return serialized


def _finalize_optimization_payload(
    building,
    design_standard,
    mode,
    best_beam_candidates,
    best_column_candidates,
    meta,
    input_snapshot,
    include_column_buckling=False,
    column_buckling_K=1.0,
):
    print(f"DEBUG: _finalize_optimization_payload - calling run_analysis with building num_storeys={building.num_storeys}")
    results, summary = run_analysis(
    building,
    design_standard,
    governing_basis="utilization",
    include_column_buckling=include_column_buckling,
    column_buckling_K=column_buckling_K,
)
    print(f"DEBUG: run_analysis returned: results type={type(results)}, summary type={type(summary)}, summary={summary}")

    if summary is None:
        return {
            "building": building,
            "results": [],
            "summary": None,
            "mode": mode,
            "best_beam_designs": [],
            "best_column_designs": [],
            "meta": meta,
            "storage": None,
        }

    excel_path = write_optimization_results(
        results=results,
        summary=summary,
        filename=None,
        settings=input_snapshot,
        mode=mode,
    )

    run_id, storage_path = save_optimization_run(
        results=results,
        summary=summary,
        input_snapshot=input_snapshot,
        mode=mode,
        excel_path=str(excel_path),
    )

    return {
        "building": building,
        "results": results,
        "summary": summary,
        "mode": mode,
        "best_beam_designs": _serialize_group_designs(best_beam_candidates),
        "best_column_designs": _serialize_group_designs(best_column_candidates),
        "meta": meta,
        "storage": {
            "results_path": str(storage_path),
            "excel_path": str(excel_path),
            "run_id": run_id,
        },
    }


def run_grouped_optimization(
    base_building,
    design_standard,
    beam_groups,
    column_groups,
    beam_shapes,
    column_shapes,
    beam_min_grade,
    beam_max_grade,
    column_min_grade,
    column_max_grade,
    u_min,
    u_max,
    max_beam_candidates_per_shape=8,
    max_column_candidates_per_shape=8,
    beam_class_rules=None,
    column_class_rules=None,
    include_column_buckling=False,
    column_buckling_K=1.0,
    verbose=False,
):
    del verbose

    beam_groups = _normalize_groups(beam_groups, base_building.num_storeys)
    column_groups = _normalize_groups(column_groups, base_building.num_storeys)

    beam_sections = _get_sections_for_shapes(
        beam_shapes,
        max_per_shape=max_beam_candidates_per_shape,
    )
    column_sections = _get_sections_for_shapes(
        column_shapes,
        max_per_shape=max_column_candidates_per_shape,
    )
    beam_materials = _get_materials(beam_min_grade, beam_max_grade)
    column_materials = _get_materials(column_min_grade, column_max_grade)

    print("DEBUG: beam Loaded materials:", [(m.grade, m.fy) for m in beam_materials])
    print("DEBUG: column Loaded materials:", [(m.grade, m.fy) for m in column_materials])
    print("DEBUG: beam_shapes =", beam_shapes, "beam_sections =", len(beam_sections))
    print("DEBUG: column_shapes =", column_shapes, "column_sections =", len(column_sections))

    sections_by_name = {section.name: section for section in beam_sections + column_sections}
    materials_by_grade = {material.grade: material for material in beam_materials + column_materials}

    beam_candidates = []
    column_candidates = []

    for group in beam_groups:
        candidates = _evaluate_beam_group(
            building=base_building,
            design_standard=design_standard,
            group_storeys=group,
            sections=beam_sections,
            materials=beam_materials,
            u_min=u_min,
            u_max=u_max,
            class_rules=beam_class_rules or [],
        )
        if not candidates:
            return {
                "building": base_building,
                "results": [],
                "summary": None,
                "mode": "Grouped Optimization",
                "best_beam_designs": [],
                "best_column_designs": [],
                "meta": {
                    "checked_combinations": 0,
                    "feasible_combinations": 0,
                    "failure_reason": f"No feasible beam design for group {group}.",
                },
                "storage": None,
            }
        beam_candidates.append(candidates)

    for group in column_groups:
        candidates = _evaluate_column_group(
            building=base_building,
            design_standard=design_standard,
            group_storeys=group,
            sections=column_sections,
            materials=column_materials,
            u_min=u_min,
            u_max=u_max,
            class_rules=column_class_rules or [],
            include_column_buckling=include_column_buckling,
            column_k=column_buckling_K,
        )
        print(f"DEBUG: Column group {group} - evaluated {len(column_sections)} sections, {len(column_materials)} materials, generated {len(candidates)} candidates")
        if candidates:
            print(f"DEBUG: Cheapest column candidate: {candidates[0].section_name} {candidates[0].grade} cost={candidates[0].total_cost}")
        if not candidates:
            return {
                "building": base_building,
                "results": [],
                "summary": None,
                "mode": "Grouped Optimization",
                "best_beam_designs": [],
                "best_column_designs": [],
                "meta": {
                    "checked_combinations": 0,
                    "feasible_combinations": 0,
                    "failure_reason": f"No feasible column design for group {group}.",
                },
                "storage": None,
            }
        column_candidates.append(candidates)

    best_beam_candidates = [candidates[0] for candidates in beam_candidates]
    best_column_candidates = [candidates[0] for candidates in column_candidates]

    building = _apply_designs_to_building(
        base_building=base_building,
        beam_designs=[_candidate_to_design(candidate, sections_by_name, materials_by_grade) for candidate in best_beam_candidates],
        beam_groups=beam_groups,
        column_designs=[_candidate_to_design(candidate, sections_by_name, materials_by_grade) for candidate in best_column_candidates],
        column_groups=column_groups,
    )

    checked_combinations = prod(len(candidates) for candidates in beam_candidates + column_candidates)
    feasible_combinations = 1 if checked_combinations > 0 else 0

    input_snapshot = {
        "num_storeys": base_building.num_storeys,
        "span": base_building.span,
        "design_standard": design_standard.code,
        "constraints": {
            "u_min": u_min,
            "u_max": u_max,
            "beam_groups": beam_groups,
            "column_groups": column_groups,
            "beam_shapes": beam_shapes,
            "column_shapes": column_shapes,
            "beam_grade_range": [f"S{beam_min_grade}", f"S{beam_max_grade}"],
            "column_grade_range": [f"S{column_min_grade}", f"S{column_max_grade}"],
            "beam_class_rules": beam_class_rules or [],
            "column_class_rules": column_class_rules or [],
            "include_column_buckling": include_column_buckling,
            "column_buckling_K": column_buckling_K,
        },
    }

    return _finalize_optimization_payload(
        building=building,
        design_standard=design_standard,
        mode="Grouped Optimization",
        best_beam_candidates=best_beam_candidates,
        best_column_candidates=best_column_candidates,
        meta={
            "checked_combinations": int(checked_combinations),
            "feasible_combinations": int(feasible_combinations),
        },
        input_snapshot=input_snapshot,
        include_column_buckling=include_column_buckling,
        column_buckling_K=column_buckling_K,
    )



def run_storeywise_greedy_optimization(
    base_building,
    design_standard,
    beam_shapes,
    column_shapes,
    beam_min_grade,
    beam_max_grade,
    column_min_grade,
    column_max_grade,
    u_min,
    u_max,
    max_beam_candidates_per_shape=8,
    max_column_candidates_per_shape=8,
    beam_class_rules=None,
    column_class_rules=None,
    include_column_buckling=False,
    column_buckling_K=1.0,
):
    return run_grouped_optimization(
        base_building=base_building,
        design_standard=design_standard,
        beam_groups=individual_storey_groups(base_building.num_storeys),
        column_groups=individual_storey_groups(base_building.num_storeys),
        beam_shapes=beam_shapes,
        column_shapes=column_shapes,
        beam_min_grade=beam_min_grade,
        beam_max_grade=beam_max_grade,
        column_min_grade=column_min_grade,
        column_max_grade=column_max_grade,
        u_min=u_min,
        u_max=u_max,
        max_beam_candidates_per_shape=max_beam_candidates_per_shape,
        max_column_candidates_per_shape=max_column_candidates_per_shape,
        beam_class_rules=beam_class_rules,
        column_class_rules=column_class_rules,
        include_column_buckling=include_column_buckling,
        column_buckling_K=column_buckling_K,
    )
 