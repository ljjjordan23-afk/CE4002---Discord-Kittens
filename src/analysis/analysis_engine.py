def run_analysis(building, design_standard):
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

    governing_member_type = None
    governing_storey = None
    governing_utilization = -1.0

    # Run calculations in normal storey order
    for item in storey_data:
        storey = item["storey"]
        w = item["w"]
        P = item["column_force"]

        beam = storey.beam
        col_left = storey.column_left
        col_right = storey.column_right

        beam_stress = beam.max_stress(w, building.span)
        beam_util = beam.utilization(w, building.span)
        beam_cost = beam.cost()

        col_stress = col_left.max_stress(P)
        col_util = col_left.utilization(P)
        col_left_cost = col_left.cost()
        col_right_cost = col_right.cost()

        storey_total_cost = beam_cost + col_left_cost + col_right_cost
        total_cost += storey_total_cost

        # Governing member check
        if beam_util > governing_utilization:
            governing_utilization = beam_util
            governing_member_type = "Beam"
            governing_storey = storey.level

        if col_util > governing_utilization:
            governing_utilization = col_util
            governing_member_type = "Column"
            governing_storey = storey.level

        results.append({
            "storey": storey.level,
            "height_m": storey.height,
            "dead_load_kN_per_m": storey.dead_load,
            "live_load_kN_per_m": storey.live_load,
            "design_load_kN_per_m": w,

            "beam_section": beam.section.name,
            "beam_grade": beam.material.grade,
            "beam_stress_MPa": beam_stress,
            "beam_utilization": beam_util,
            "beam_cost_SGD": beam_cost,

            "column_section": col_left.section.name,
            "column_grade": col_left.material.grade,
            "column_force_kN": P,
            "column_stress_MPa": col_stress,
            "column_utilization": col_util,
            "column_left_cost_SGD": col_left_cost,
            "column_right_cost_SGD": col_right_cost,

            "storey_total_cost_SGD": storey_total_cost
        })

    summary = {
        "num_storeys": building.num_storeys,
        "span_m": building.span,
        "total_cost_SGD": total_cost,
        "max_utilization": governing_utilization,
        "governing_member_type": governing_member_type,
        "governing_storey": governing_storey
    }

    return results, summary