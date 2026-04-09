from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from src.io.input_handler import load_module1_input, build_building_from_module1
from src.analysis.analysis_engine import run_analysis
from src.database.db_query import (
    get_all_section_names,
    get_all_material_grades,
    get_all_design_standard_codes,
)
from src.optimization.optimizer import (
    run_grouped_optimization,
    run_individual_storey_sequential_optimization,
)


def build_member_options(results):
    options = []
    for r in results:
        options.append(f"Beam - Storey {r['storey']}")
        options.append(f"Column - Storey {r['storey']}")
    return options

def parse_selected_member(selected_text):
    member_type, storey_text = selected_text.split(" - ")
    storey = int(storey_text.replace("Storey ", ""))
    return member_type, storey

def get_selected_result(results, member_type, storey):
    for r in results:
        if r["storey"] == storey:
            return r
    return None

def get_member_color(utilization):
    if utilization < 0.6:
        return "green"
    elif utilization < 0.8:
        return "orange"
    else:
        return "red"

def utilization_band_text(utilization):
    if utilization < 0.6:
        return "Low"
    elif utilization < 0.8:
        return "Moderate"
    else:
        return "High"

def create_interactive_frame(building, results, selected_member_type, selected_storey):
    fig = go.Figure()
    results = sorted(results, key=lambda x: x["storey"])

    x_left = 0
    x_right = building.span
    current_y = 0

    for r in results:
        storey_height = r["height_m"]
        next_y = current_y + storey_height

        beam_color = get_member_color(r["beam_utilization"])
        col_color = get_member_color(r["column_utilization"])

        beam_selected = (selected_member_type == "Beam" and selected_storey == r["storey"])
        col_selected = (selected_member_type == "Column" and selected_storey == r["storey"])

        beam_width = 10 if beam_selected else 6
        col_width = 10 if col_selected else 6

        beam_opacity = 1.0 if beam_selected else 0.8
        col_opacity = 1.0 if col_selected else 0.8

        fig.add_trace(go.Scatter(
            x=[x_left, x_left],
            y=[current_y, next_y],
            mode="lines",
            line=dict(color=col_color, width=col_width),
            opacity=col_opacity,
            hoverinfo="text",
            text=(
                f"<b>Column - Storey {r['storey']}</b><br>"
                f"Section: {r['column_section']}<br>"
                f"Grade: {r['column_grade']}<br>"
                f"Force: {r['column_force_kN']:.3f} kN<br>"
                f"Stress: {r['column_stress_MPa']:.3f} MPa<br>"
                f"Utilization: {r['column_utilization']:.3f}"
            ),
            showlegend=False
        ))

        fig.add_trace(go.Scatter(
            x=[x_right, x_right],
            y=[current_y, next_y],
            mode="lines",
            line=dict(color=col_color, width=col_width),
            opacity=col_opacity,
            hoverinfo="text",
            text=(
                f"<b>Column - Storey {r['storey']}</b><br>"
                f"Section: {r['column_section']}<br>"
                f"Grade: {r['column_grade']}<br>"
                f"Force: {r['column_force_kN']:.3f} kN<br>"
                f"Stress: {r['column_stress_MPa']:.3f} MPa<br>"
                f"Utilization: {r['column_utilization']:.3f}"
            ),
            showlegend=False
        ))

        fig.add_trace(go.Scatter(
            x=[x_left, x_right],
            y=[next_y, next_y],
            mode="lines",
            line=dict(color=beam_color, width=beam_width),
            opacity=beam_opacity,
            hoverinfo="text",
            text=(
                f"<b>Beam - Storey {r['storey']}</b><br>"
                f"Section: {r['beam_section']}<br>"
                f"Grade: {r['beam_grade']}<br>"
                f"Stress: {r['beam_stress_MPa']:.3f} MPa<br>"
                f"Utilization: {r['beam_utilization']:.3f}<br>"
                f"Cost: {r['beam_cost_SGD']:.3f} SGD"
            ),
            showlegend=False
        ))

        beam_label = f"{r['beam_section']}<br>U={r['beam_utilization']:.3f}"
        if beam_selected:
            beam_label = f"<b>{beam_label}</b>"

        fig.add_annotation(
            x=building.span / 2,
            y=next_y + 0.18,
            text=beam_label,
            showarrow=False,
            font=dict(size=14),
            align="center"
        )

        current_y = next_y

    fig.update_layout(
        title="Interactive Steel Frame Viewer",
        xaxis_title="Span (m)",
        yaxis_title="Height (m)",
        xaxis=dict(range=[-1.7, building.span + 1.7]),
        yaxis=dict(range=[0, current_y + 1]),
        template="plotly_dark",
        height=780,
        margin=dict(l=40, r=40, t=60, b=40)
    )

    return fig

def show_utilization_legend():
    st.markdown("### Utilization Bands")
    st.markdown(
        """
        <div style="display:flex; flex-direction:column; gap:10px;">
            <div style="display:flex; align-items:center; gap:10px;">
                <div style="width:28px; height:16px; background:green; border-radius:4px;"></div>
                <div><b>U &lt; 0.6</b> — Low</div>
            </div>
            <div style="display:flex; align-items:center; gap:10px;">
                <div style="width:28px; height:16px; background:orange; border-radius:4px;"></div>
                <div><b>0.6 ≤ U &lt; 0.8</b> — Moderate</div>
            </div>
            <div style="display:flex; align-items:center; gap:10px;">
                <div style="width:28px; height:16px; background:red; border-radius:4px;"></div>
                <div><b>U ≥ 0.8</b> — High</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

def draw_beam_schematic(result):
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0.15, y0=0.78, x1=0.85, y1=0.90,
                  line=dict(color="white", width=3), fillcolor="rgba(180,180,180,0.35)")
    fig.add_shape(type="rect", x0=0.46, y0=0.20, x1=0.54, y1=0.78,
                  line=dict(color="white", width=3), fillcolor="rgba(180,180,180,0.35)")
    fig.add_shape(type="rect", x0=0.15, y0=0.08, x1=0.85, y1=0.20,
                  line=dict(color="white", width=3), fillcolor="rgba(180,180,180,0.35)")

    fig.add_annotation(x=0.5, y=1.02, text=f"<b>{result['beam_section']}</b>", showarrow=False, font=dict(size=13))
    fig.add_annotation(x=0.5, y=-0.05, text="I-section schematic", showarrow=False, font=dict(size=11, color="lightgray"))

    fig.update_xaxes(visible=False, range=[0, 1])
    fig.update_yaxes(visible=False, range=[0, 1.08])
    fig.update_layout(template="plotly_dark", height=240, margin=dict(l=10, r=10, t=20, b=20))
    return fig

def draw_column_schematic(result):
    fig = go.Figure()
    section_name = result["column_section"]

    if "SHS" in section_name:
        fig.add_shape(type="rect", x0=0.22, y0=0.22, x1=0.78, y1=0.78, line=dict(color="white", width=3))
        fig.add_shape(type="rect", x0=0.38, y0=0.38, x1=0.62, y1=0.62, line=dict(color="white", width=3))
        footer = "SHS hollow section"
    elif "CHS" in section_name:
        fig.add_shape(type="circle", x0=0.22, y0=0.22, x1=0.78, y1=0.78, line=dict(color="white", width=3))
        fig.add_shape(type="circle", x0=0.38, y0=0.38, x1=0.62, y1=0.62, line=dict(color="white", width=3))
        footer = "CHS hollow section"
    else:
        fig.add_shape(type="rect", x0=0.30, y0=0.12, x1=0.70, y1=0.88, line=dict(color="white", width=3))
        footer = "Column section schematic"

    fig.add_annotation(x=0.5, y=1.02, text=f"<b>{section_name}</b>", showarrow=False, font=dict(size=13))
    fig.add_annotation(x=0.5, y=-0.05, text=footer, showarrow=False, font=dict(size=11, color="lightgray"))

    fig.update_xaxes(visible=False, range=[0, 1])
    fig.update_yaxes(visible=False, range=[0, 1.08], scaleanchor="x", scaleratio=1)
    fig.update_layout(template="plotly_dark", height=240, margin=dict(l=10, r=10, t=20, b=20))
    return fig

def show_member_details(result, selected_member_type):
    st.subheader("Selected Member Details")

    if selected_member_type == "Beam":
        band = utilization_band_text(result["beam_utilization"])
        st.caption("This panel shows the actual selected member from the current result, not just the search family.")
        st.markdown(f"**Member type:** Beam")
        st.markdown(f"**Storey:** {result['storey']}")
        st.markdown(f"**Section:** {result['beam_section']}")
        st.markdown(f"**Grade:** {result['beam_grade']}")
        st.markdown(f"**Stress:** {result['beam_stress_MPa']:.3f} MPa")
        st.markdown(f"**Utilization:** {result['beam_utilization']:.3f} ({band})")
        st.markdown(f"**Cost:** {result['beam_cost_SGD']:.3f} SGD")
        st.plotly_chart(draw_beam_schematic(result), use_container_width=True)
    else:
        band = utilization_band_text(result["column_utilization"])
        st.caption("This panel shows the actual selected member from the current result, not just the search family.")
        st.markdown(f"**Member type:** Column")
        st.markdown(f"**Storey:** {result['storey']}")
        st.markdown(f"**Section:** {result['column_section']}")
        st.markdown(f"**Grade:** {result['column_grade']}")
        st.markdown(f"**Axial force:** {result['column_force_kN']:.3f} kN")
        st.markdown(f"**Stress:** {result['column_stress_MPa']:.3f} MPa")
        st.markdown(f"**Utilization:** {result['column_utilization']:.3f} ({band})")
        st.plotly_chart(draw_column_schematic(result), use_container_width=True)

def build_sidebar_input(default_data, all_sections, all_grades, all_codes):
    st.sidebar.header("Frame Input")

    num_storeys = st.sidebar.number_input(
        "Number of storeys",
        min_value=1,
        max_value=20,
        value=int(default_data["num_storeys"]),
        step=1
    )

    span = st.sidebar.number_input(
        "Span (m)",
        min_value=1.0,
        max_value=20.0,
        value=float(default_data["span"]),
        step=0.5
    )

    design_standard = st.sidebar.selectbox(
        "Design standard",
        all_codes,
        index=all_codes.index(default_data["design_standard"]) if default_data["design_standard"] in all_codes else 0
    )

    st.sidebar.markdown("---")
    st.sidebar.header("Mode")

    run_mode = st.sidebar.selectbox(
        "Select mode",
        ["Analysis", "Grouped Optimization", "Individual-Storey Optimization"],
        index=0
)

    beam_shape = "I"
    st.sidebar.selectbox("Beam shape", ["I"], index=0, disabled=True)

    column_shape = st.sidebar.selectbox(
        "Column shape",
        ["SHS", "CHS"],
        index=0
)


    candidate_pool = st.sidebar.number_input(
        "Candidate pool size",
        min_value=2,
        max_value=30,
        value=8,
        step=1
    )

    default_storeys = default_data["storeys"]

    rows = []
    for i in range(num_storeys):
        if i < len(default_storeys):
            d = default_storeys[i]
        else:
            d = {
                "level": i + 1,
                "height": 3.0,
                "dead_load": 5.0,
                "live_load": 3.0,
                "beam_section": all_sections[0],
                "beam_grade": all_grades[0],
                "column_section": all_sections[0],
                "column_grade": all_grades[0]
            }

        with st.sidebar.expander(f"Storey {i+1}", expanded=False):
            level = i + 1
            height = st.number_input(f"Height S{level}", value=float(d["height"]), step=0.5, key=f"h_{level}")
            dead_load = st.number_input(f"Dead load S{level}", value=float(d["dead_load"]), step=0.5, key=f"d_{level}")
            live_load = st.number_input(f"Live load S{level}", value=float(d["live_load"]), step=0.5, key=f"l_{level}")

            beam_section = st.selectbox(
                f"Beam section S{level}",
                all_sections,
                index=all_sections.index(d["beam_section"]) if d["beam_section"] in all_sections else 0,
                key=f"bs_{level}"
            )

            beam_grade = st.selectbox(
                f"Beam grade S{level}",
                all_grades,
                index=all_grades.index(d["beam_grade"]) if d["beam_grade"] in all_grades else 0,
                key=f"bg_{level}"
            )

            column_section = st.selectbox(
                f"Column section S{level}",
                all_sections,
                index=all_sections.index(d["column_section"]) if d["column_section"] in all_sections else 0,
                key=f"cs_{level}"
            )

            column_grade = st.selectbox(
                f"Column grade S{level}",
                all_grades,
                index=all_grades.index(d["column_grade"]) if d["column_grade"] in all_grades else 0,
                key=f"cg_{level}"
            )

            rows.append({
                "level": level,
                "height": height,
                "dead_load": dead_load,
                "live_load": live_load,
                "beam_section": beam_section,
                "beam_grade": beam_grade,
                "column_section": column_section,
                "column_grade": column_grade
            })
    constraints = build_constraints_input(num_storeys)

    return {
        "num_storeys": num_storeys,
        "span": span,
        "design_standard": design_standard,
        "storeys": rows,
        "run_mode": run_mode,
        "beam_shape": beam_shape,
        "column_shape": column_shape,
        "candidate_pool": candidate_pool,
        "constraints": constraints
    }

def format_storey_group(group):
    if len(group) == 1:
        return f"Storey {group[0]}"
    return "Storeys " + ", ".join(str(x) for x in group)

def get_group_labels(num_storeys):
    """
    Mirrors the default grouping logic used in main().
    """
    if num_storeys == 1:
        beam_groups = [[1]]
        column_groups = [[1]]
    elif num_storeys == 2:
        beam_groups = [[1], [2]]
        column_groups = [[1], [2]]
    elif num_storeys >= 5:
        beam_groups = [[1], list(range(2, num_storeys)), [num_storeys]]
        column_groups = [list(range(1, num_storeys)), [num_storeys]]
    else:
        beam_groups = [[i] for i in range(1, num_storeys + 1)]
        column_groups = [[i] for i in range(1, num_storeys + 1)]

    return beam_groups, column_groups

def groups_to_text(groups):
    parts = []
    for group in groups:
        if len(group) == 1:
            parts.append(str(group[0]))
        else:
            # compress consecutive ranges like [2,3,4] -> "2-4"
            if group == list(range(group[0], group[-1] + 1)):
                parts.append(f"{group[0]}-{group[-1]}")
            else:
                parts.append(",".join(str(x) for x in group))
    return " | ".join(parts)

def show_optimization_settings(input_data):
    st.subheader("Optimization Settings")
    st.markdown(f"**Mode:** {input_data['run_mode']}")
    st.markdown(f"**Beam shape searched:** {input_data['beam_shape']} (fixed)")
    st.markdown(f"**Column shape searched:** {input_data['column_shape']}")
    st.markdown(f"**Utilization lower bound:** {input_data['constraints']['u_min']:.2f}")
    st.markdown(f"**Utilization upper bound:** {input_data['constraints']['u_max']:.2f}")
    st.markdown(f"**Candidate pool size:** {int(input_data['candidate_pool'])}")

def show_optimization_summary(input_data, optimization_result):
    if optimization_result is None:
        return

    st.subheader("Optimization Summary")

    # Show optimized overall result
    if optimization_result.get("summary") is not None:
        st.markdown(f"**Optimized total cost:** {optimization_result['summary']['total_cost_SGD']:.3f} SGD")
        st.markdown(f"**Optimized max utilization:** {optimization_result['summary']['max_utilization']:.3f}")
        st.markdown(
            f"**Optimized governing member:** "
            f"{optimization_result['summary']['governing_member_type']} "
            f"at Storey {optimization_result['summary']['governing_storey']}"
        )

    mode = input_data["run_mode"]

    if mode == "Grouped Optimization":
        beam_groups = input_data["constraints"]["beam_groups"]
        column_groups = input_data["constraints"]["column_groups"]

        if optimization_result.get("best_beam_designs"):
            st.markdown("**Optimized Beam Designs**")
            for i, d in enumerate(optimization_result["best_beam_designs"], start=1):
                group_text = format_storey_group(beam_groups[i - 1])
                st.markdown(
                    f"- **Beam Group {i} ({group_text})**: {d['section']} | {d['grade']}"
                )

        if optimization_result.get("best_column_designs"):
            st.markdown("**Optimized Column Designs**")
            for i, d in enumerate(optimization_result["best_column_designs"], start=1):
                group_text = format_storey_group(column_groups[i - 1])
                st.markdown(
                    f"- **Column Group {i} ({group_text})**: {d['section']} | {d['grade']}"
                )

    elif mode == "Individual-Storey Optimization":
        if optimization_result.get("best_beam_sections"):
            st.markdown("**Optimized Beam Sections by Storey**")
            for i, sec in enumerate(optimization_result["best_beam_sections"], start=1):
                st.markdown(f"- **Storey {i} Beam**: {sec}")

        if optimization_result.get("best_column_sections"):
            st.markdown("**Optimized Column Sections by Storey**")
            for i, sec in enumerate(optimization_result["best_column_sections"], start=1):
                st.markdown(f"- **Storey {i} Column**: {sec}")

def parse_group_string(group_text):
    """
    Example:
    '1 | 2-4 | 5' -> [[1], [2,3,4], [5]]
    """
    groups = []
    parts = [p.strip() for p in group_text.split("|") if p.strip()]

    for part in parts:
        storeys = []
        subparts = [s.strip() for s in part.split(",") if s.strip()]

        for sp in subparts:
            if "-" in sp:
                a, b = sp.split("-")
                a = int(a.strip())
                b = int(b.strip())
                storeys.extend(list(range(a, b + 1)))
            else:
                storeys.append(int(sp))

        groups.append(sorted(list(set(storeys))))

    return groups

def parse_class_list(class_text):
    """
    Example:
    '1,2' -> [1,2]
    """
    return [int(x.strip()) for x in class_text.split(",") if x.strip()]

def build_constraints_input(num_storeys):
    st.sidebar.markdown("---")
    st.sidebar.header("Optimization Constraints")

    u_min = st.sidebar.number_input(
        "Utilization lower bound",
        min_value=0.0,
        max_value=1.5,
        value=0.5,
        step=0.05
    )

    u_max = st.sidebar.number_input(
        "Utilization upper bound",
        min_value=0.0,
        max_value=1.5,
        value=0.7,
        step=0.05
    )

    default_beam_groups, default_column_groups = get_group_labels(num_storeys)
    default_beam_group_text = groups_to_text(default_beam_groups)
    default_column_group_text = groups_to_text(default_column_groups)

    beam_group_text = st.sidebar.text_input(
        "Beam groups",
        value=default_beam_group_text
    )

    column_group_text = st.sidebar.text_input(
        "Column groups",
        value=default_column_group_text
    )

    min_grade = st.sidebar.selectbox(
        "Minimum steel grade",
        ["S235", "S275", "S355", "S420", "S460"],
        index=0
    )

    max_grade = st.sidebar.selectbox(
        "Maximum steel grade",
        ["S235", "S275", "S355", "S420", "S460"],
        index=2
    )
    if int(min_grade.replace("S", "")) > int(max_grade.replace("S", "")):
        st.sidebar.error("Minimum steel grade cannot be higher than maximum steel grade.")

    allowed_beam_shapes = ["I"]
    st.sidebar.multiselect(
        "Allowed beam shapes",
        ["I"],
        default=["I"],
        disabled=True
    )

    allowed_column_shapes = st.sidebar.multiselect(
        "Allowed column shapes",
        ["SHS", "CHS"],
        default=["SHS", "CHS"]
    )

    class_rule_storey_text = st.sidebar.text_input(
        "Column class rule storeys",
        value="1-3"
    )

    class_rule_allowed_text = st.sidebar.text_input(
        "Allowed column classes for those storeys",
        value="1,2"
    )

    constraints = {
        "u_min": u_min,
        "u_max": u_max,
        "beam_groups": parse_group_string(beam_group_text),
        "column_groups": parse_group_string(column_group_text),
        "min_grade": min_grade,
        "max_grade": max_grade,
        "allowed_beam_shapes": allowed_beam_shapes,
        "allowed_column_shapes": allowed_column_shapes,
        "column_class_rules": [
            {
                "storeys": parse_group_string(class_rule_storey_text.replace("|", ","))[0],
                "allowed_classes": parse_class_list(class_rule_allowed_text)
            }
        ]
    }

    return constraints

def main():
    st.set_page_config(page_title="CE3204 Interactive Frame Viewer", layout="wide")

    default_data = load_module1_input("input_module1.json")
    all_sections = get_all_section_names()
    all_grades = get_all_material_grades()
    all_codes = get_all_design_standard_codes()

    input_data = build_sidebar_input(default_data, all_sections, all_grades, all_codes)

    if int(input_data["constraints"]["min_grade"].replace("S", "")) > int(input_data["constraints"]["max_grade"].replace("S", "")):
        st.error("Invalid grade range: minimum steel grade is higher than maximum steel grade.")
        return

    st.title("CE3204 Interactive Frame Viewer")

    try:
        building, design = build_building_from_module1(input_data)
    except Exception as e:
        st.error(f"Input/build error: {e}")
        return

    optimization_result = None

    try:
        if input_data["run_mode"] == "Analysis":
            results, summary = run_analysis(building, design)

        elif input_data["run_mode"] == "Grouped Optimization":
            optimization_result = run_grouped_optimization(
                base_building=building,
                design_standard=design,
                beam_groups=input_data["constraints"]["beam_groups"],
                column_groups=input_data["constraints"]["column_groups"],
                beam_shape=input_data["beam_shape"],
                column_shape=input_data["column_shape"],
                beam_min_grade=input_data["constraints"]["min_grade"],
                beam_max_grade=input_data["constraints"]["max_grade"],
                column_min_grade=input_data["constraints"]["min_grade"],
                column_max_grade=input_data["constraints"]["max_grade"],
                u_min=input_data["constraints"]["u_min"],
                u_max=input_data["constraints"]["u_max"],
                max_beam_candidates=int(input_data["candidate_pool"]),
                max_column_candidates=int(input_data["candidate_pool"]),
                column_class_rules=input_data["constraints"]["column_class_rules"],
            )

            if optimization_result["summary"] is None:
                st.error("No feasible grouped optimization design found.")
                return

            building = optimization_result["building"]
            results = optimization_result["results"]
            summary = optimization_result["summary"]

        else:  # Individual-Storey Optimization
            optimization_result = run_individual_storey_sequential_optimization(
                base_building=building,
                design_standard=design,
                beam_shape=input_data["beam_shape"],
                column_shape=input_data["column_shape"],
                u_min=input_data["constraints"]["u_min"],
                u_max=input_data["constraints"]["u_max"],
                max_beam_candidates=int(input_data["candidate_pool"]),
                max_column_candidates=int(input_data["candidate_pool"])
            )

            if optimization_result["summary"] is None:
                st.error("No feasible individual-storey optimization design found.")
                return

            building = optimization_result["building"]
            results = optimization_result["results"]
            summary = optimization_result["summary"]

    except Exception as e:
        st.error(f"Analysis/optimization error: {e}")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Cost (SGD)", f"{summary['total_cost_SGD']:.3f}")
    c2.metric("Max Utilization", f"{summary['max_utilization']:.3f}")
    c3.metric("Governing Member", f"{summary['governing_member_type']} @ Storey {summary['governing_storey']}")

    st.markdown("---")

    member_options = build_member_options(results)
    selected_text = st.selectbox("Select member to inspect", member_options)

    selected_member_type, selected_storey = parse_selected_member(selected_text)
    selected_result = get_selected_result(results, selected_member_type, selected_storey)

    left, right = st.columns([2.3, 1])

    with left:
        fig = create_interactive_frame(building, results, selected_member_type, selected_storey)
        st.plotly_chart(fig, use_container_width=True)

    with right:
        show_utilization_legend()
        st.markdown("---")
        show_member_details(selected_result, selected_member_type)

        st.subheader("Governing Member")
        st.markdown(f"**Type:** {summary['governing_member_type']}")
        st.markdown(f"**Storey:** {summary['governing_storey']}")
        st.markdown(f"**Utilization:** {summary['max_utilization']:.3f}")

        if optimization_result is not None:
            st.markdown("---")
            show_optimization_settings(input_data)
            st.markdown("---")
            show_optimization_summary(input_data, optimization_result)

    st.markdown("---")
    st.subheader("Results Table")
    st.dataframe(pd.DataFrame(results).round(3), use_container_width=True)

if __name__ == "__main__":
    main()