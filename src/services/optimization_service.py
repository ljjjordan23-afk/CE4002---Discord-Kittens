from src.optimization.optimizer import (
    run_grouped_optimization,
    run_storeywise_greedy_optimization,
)


def run_optimization_service(building, design_standard, input_data):
    constraints = input_data["constraints"]
    min_grade_val = int(constraints["min_grade"].replace("S", ""))
    max_grade_val = int(constraints["max_grade"].replace("S", ""))
    mode = input_data["run_mode"]

    # Support optional toggles to disable class rules
    beam_class_rules_enabled = input_data.get("beam_class_rules_enabled", True)
    column_class_rules_enabled = input_data.get("column_class_rules_enabled", True)

    # Get class rules, or empty list if disabled
    beam_class_rules = constraints.get("beam_class_rules", []) if beam_class_rules_enabled else []
    column_class_rules = constraints.get("column_class_rules", []) if column_class_rules_enabled else []

    print("DEBUG: run_optimization_service start")
    print("DEBUG: mode =", mode)
    print("DEBUG: u_min =", constraints["u_min"], "u_max =", constraints["u_max"])
    print("DEBUG: grade range =", constraints["min_grade"], "-", constraints["max_grade"])
    print("DEBUG: candidate_pool =", input_data["candidate_pool"])
    print("DEBUG: allowed_beam_shapes =", constraints["allowed_beam_shapes"])
    print("DEBUG: allowed_column_shapes =", constraints["allowed_column_shapes"])
    print("DEBUG: beam_groups =", constraints.get("beam_groups"))
    print("DEBUG: column_groups =", constraints.get("column_groups"))
    print("DEBUG: beam_class_rules_enabled =", beam_class_rules_enabled, "beam_class_rules =", beam_class_rules)
    print("DEBUG: column_class_rules_enabled =", column_class_rules_enabled, "column_class_rules =", column_class_rules)

    if mode == "Grouped Optimization":
        result = run_grouped_optimization(
            base_building=building,
            design_standard=design_standard,
            beam_groups=constraints["beam_groups"],
            column_groups=constraints["column_groups"],
            beam_shapes=constraints["allowed_beam_shapes"],
            column_shapes=constraints["allowed_column_shapes"],
            beam_min_grade=min_grade_val,
            beam_max_grade=max_grade_val,
            column_min_grade=min_grade_val,
            column_max_grade=max_grade_val,
            u_min=constraints["u_min"],
            u_max=constraints["u_max"],
            max_beam_candidates_per_shape=int(input_data["candidate_pool"]),
            max_column_candidates_per_shape=int(input_data["candidate_pool"]),
            beam_class_rules=beam_class_rules,
            column_class_rules=column_class_rules,
            verbose=False,
        )
        print("DEBUG: grouped result summary =", result.get("summary"))
        return result

    if mode == "Individual-Storey Optimization":
        result = run_storeywise_greedy_optimization(
            base_building=building,
            design_standard=design_standard,
            beam_shapes=constraints["allowed_beam_shapes"],
            column_shapes=constraints["allowed_column_shapes"],
            beam_min_grade=min_grade_val,
            beam_max_grade=max_grade_val,
            column_min_grade=min_grade_val,
            column_max_grade=max_grade_val,
            u_min=constraints["u_min"],
            u_max=constraints["u_max"],
            max_beam_candidates_per_shape=int(input_data["candidate_pool"]),
            max_column_candidates_per_shape=int(input_data["candidate_pool"]),
            beam_class_rules=beam_class_rules,
            column_class_rules=column_class_rules,
        )
        print("DEBUG: individual result summary =", result.get("summary"))
        return result

    raise ValueError(f"Unsupported optimization mode: {mode}")
