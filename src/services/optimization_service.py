from src.optimization.optimizer import (
    run_grouped_optimization,
    run_storeywise_greedy_optimization,
)


def run_optimization_service(building, design_standard, input_data):
    constraints = input_data["constraints"]
    min_grade_val = int(constraints["min_grade"].replace("S", ""))
    max_grade_val = int(constraints["max_grade"].replace("S", ""))
    mode = input_data["run_mode"]

    if mode == "Grouped Optimization":
        return run_grouped_optimization(
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
            column_class_rules=constraints["column_class_rules"],
            verbose=False,
        )

    if mode == "Individual-Storey Optimization":
        return run_storeywise_greedy_optimization(
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
            column_class_rules=constraints["column_class_rules"],
        )

    raise ValueError(f"Unsupported optimization mode: {mode}")
