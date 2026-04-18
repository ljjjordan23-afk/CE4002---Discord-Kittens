from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

import plotly.graph_objects as go
import streamlit as st
import pandas as pd
import os
from src.analysis.analysis_engine import export_results_to_excel

from src.io.input_handler import load_module1_input, build_building_from_module1
from src.database.db_query import (
    get_all_section_names,
    get_all_material_grades,
    get_all_design_standard_codes,
)
from src.services.analysis_service import run_analysis_service
from src.services.optimization_service import run_optimization_service
from src.optimization.optimizer import individual_storey_groups




@st.cache_data
def get_cached_section_names():
    return get_all_section_names()


@st.cache_data
def get_cached_material_grades():
    return get_all_material_grades()


@st.cache_data
def get_cached_design_standard_codes():
    return get_all_design_standard_codes()


def initialize_app_state():
    defaults = {
        "computed_payload": None,
        "last_mode": None,
        "last_run_signature": None,
        "last_error": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_computed_payload():
    st.session_state["computed_payload"] = None
    st.session_state["last_run_signature"] = None
    st.session_state["last_error"] = None


def build_run_signature(input_data):
    constraints = input_data["constraints"]
    storeys_sig = tuple(
        (
            row["level"],
            row["height"],
            row["dead_load"],
            row["live_load"],
            row["beam_section"],
            row["beam_grade"],
            row["column_section"],
            row["column_grade"],
        )
        for row in input_data["storeys"]
    )

    return (
        input_data["run_mode"],
        input_data["num_storeys"],
        input_data["span"],
        input_data["design_standard"],
        input_data["governing_basis"],
        int(input_data["candidate_pool"]),
        storeys_sig,
        constraints["u_min"],
        constraints["u_max"],
        tuple(tuple(g) for g in constraints["beam_groups"]),
        tuple(tuple(g) for g in constraints["column_groups"]),
        constraints["min_grade"],
        constraints["max_grade"],
        tuple(constraints["allowed_beam_shapes"]),
        tuple(constraints["allowed_column_shapes"]),
        tuple(
            (tuple(rule["storeys"]), tuple(rule["allowed_classes"]))
            for rule in constraints["beam_class_rules"]
        ),
        tuple(
            (tuple(rule["storeys"]), tuple(rule["allowed_classes"]))
            for rule in constraints["column_class_rules"]
        ),
        input_data.get("beam_class_rules_enabled", True),
        input_data.get("column_class_rules_enabled", True),
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
    
def get_beam_label(r, governing_basis):
    governing_basis = str(governing_basis).strip().lower()

    if governing_basis == "moment":
        return f"{r['beam_section']}<br>M={r['beam_Mmax_kNm']:.2f} kN·m"
    elif governing_basis == "stress":
        return f"{r['beam_section']}<br>σ={r['beam_stress_MPa']:.2f} MPa"
    elif governing_basis == "deflection":
        return f"{r['beam_section']}<br>δ={r.get('beam_deflection_mm', 0.0):.2f} mm"
    else:
        return f"{r['beam_section']}<br>U={r['beam_utilization']:.3f}"

def get_column_label(r):
    return f"{r['column_section']}<br>U={r['column_utilization']:.3f}"

def create_interactive_frame(building, results, selected_member_type, selected_storey, governing_basis):
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
                f"Axial load: {r['column_force_kN']:.3f} kN<br>"
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
                f"Deflection: {r.get('beam_deflection_mm', 0.0):.3f} mm<br>"
                f"Limit: L/{r.get('beam_deflection_ratio_used', 360.0):.0f} = {r.get('beam_deflection_limit_mm', 0.0):.3f} mm<br>"
                f"Check: {'PASS' if r.get('beam_deflection_ok', True) else 'FAIL'}<br>"
                f"Cost: {r['beam_cost_SGD']:.3f} SGD"
            ),
            showlegend=False
        ))

        
        beam_label = get_beam_label(r, governing_basis)
        if beam_selected:
            beam_label = f"<b>{beam_label}</b>"

        column_label = get_column_label(r)
        if col_selected:
            column_label = f"<b>{column_label}</b>"

        is_top_storey = (r["storey"] == results[-1]["storey"])

        if is_top_storey:
            label_y = next_y + 0.55
            yanchor = "bottom"
        else:
            label_y = next_y - 0.28
            yanchor = "top"

        fig.add_annotation(
            x=building.span / 2,
            y=label_y,
            text=beam_label,
            showarrow=False,
            font=dict(size=11),
            align="center",
            yanchor=yanchor
        )

        # Add column labels
        fig.add_annotation(
            x=-0.8,
            y=(current_y + next_y) / 2,
            text=column_label,
            showarrow=False,
            font=dict(size=10),
            align="center",
            xanchor="center"
        )

        fig.add_annotation(
            x=building.span + 0.8,
            y=(current_y + next_y) / 2,
            text=column_label,
            showarrow=False,
            font=dict(size=10),
            align="center",
            xanchor="center"
        )

        current_y = next_y

    fig.update_layout(
        title="Interactive Steel Frame Viewer",
        xaxis_title="Span (m)",
        yaxis_title="Height (m)",
        xaxis=dict(range=[-2.0, building.span + 2.0]),
        yaxis=dict(range=[0, current_y + 1.8]),
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
    fig.add_shape(
        type="rect", x0=0.15, y0=0.78, x1=0.85, y1=0.90,
        line=dict(color="white", width=3),
        fillcolor="rgba(180,180,180,0.35)"
    )
    fig.add_shape(
        type="rect", x0=0.46, y0=0.20, x1=0.54, y1=0.78,
        line=dict(color="white", width=3),
        fillcolor="rgba(180,180,180,0.35)"
    )
    fig.add_shape(
        type="rect", x0=0.15, y0=0.08, x1=0.85, y1=0.20,
        line=dict(color="white", width=3),
        fillcolor="rgba(180,180,180,0.35)"
    )

    fig.add_annotation(
        x=0.5, y=1.02, text=f"<b>{result['beam_section']}</b>",
        showarrow=False, font=dict(size=13)
    )
    fig.add_annotation(
        x=0.5, y=-0.05, text="I-section schematic",
        showarrow=False, font=dict(size=11, color="lightgray")
    )

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

    fig.add_annotation(
        x=0.5, y=1.02, text=f"<b>{section_name}</b>",
        showarrow=False, font=dict(size=13)
    )
    fig.add_annotation(
        x=0.5, y=-0.05, text=footer,
        showarrow=False, font=dict(size=11, color="lightgray")
    )

    fig.update_xaxes(visible=False, range=[0, 1])
    fig.update_yaxes(visible=False, range=[0, 1.08], scaleanchor="x", scaleratio=1)
    fig.update_layout(template="plotly_dark", height=240, margin=dict(l=10, r=10, t=20, b=20))
    return fig

def draw_beam_sfd_plot(result, building):
    beam = building.storeys[result["storey"] - 1].beam
    w = result["design_load_kN_per_m"]
    L = building.span

    data = beam.beam_diagram_data(w, L)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data["x_m"],
        y=data["V_kN"],
        mode="lines",
        fill="tozeroy",
        name="Shear Force"
    ))

    fig.update_layout(
        title="Beam Shear Force Diagram",
        xaxis_title="Position along beam, x (m)",
        yaxis_title="Shear Force (kN)",
        template="plotly_dark",
        height=320,
        margin=dict(l=40, r=20, t=50, b=40)
    )
    return fig

def draw_beam_bmd_plot(result, building):
    beam = building.storeys[result["storey"] - 1].beam
    w = result["design_load_kN_per_m"]
    L = building.span

    data = beam.beam_diagram_data(w, L)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data["x_m"],
        y=data["M_kNm"],
        mode="lines",
        fill="tozeroy",
        name="Bending Moment"
    ))

    fig.update_layout(
        title="Beam Bending Moment Diagram",
        xaxis_title="Position along beam, x (m)",
        yaxis_title="Bending Moment (kN·m)",
        template="plotly_dark",
        height=320,
        margin=dict(l=40, r=20, t=50, b=40)
    )
    return fig

def draw_beam_deflection_plot(result, building):
    beam = building.storeys[result["storey"] - 1].beam
    w = result["design_load_kN_per_m"]
    L = building.span

    data = beam.beam_diagram_data(w, L)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data["x_m"],
        y=data["y_mm"],
        mode="lines",
        name="Deflection"
    ))

    fig.update_layout(
        title="Beam Deflection Curve",
        xaxis_title="Position along beam, x (m)",
        yaxis_title="Deflection (mm)",
        template="plotly_dark",
        height=320,
        margin=dict(l=40, r=20, t=50, b=40)
    )
    return fig

def show_member_details(result, selected_member_type, building):
    st.subheader("Selected Member Details")
   

    if selected_member_type == "Beam":
        band = utilization_band_text(result["beam_utilization"])
        limit_mm = result.get("beam_deflection_limit_mm", 0.0)
        limit_ratio = result.get("beam_deflection_ratio_used", 360.0)
        ok = result.get("beam_deflection_ok", True)

   
        st.caption("This panel shows the actual selected member from the current result, not just the search family.")
        st.markdown("**Member type:** Beam")
        st.markdown(f"**Storey:** {result['storey']}")
        st.markdown(f"**Section:** {result['beam_section']}")
        st.markdown(f"**Grade:** {result['beam_grade']}")
        st.markdown(f"**Stress:** {result['beam_stress_MPa']:.3f} MPa")
        st.markdown(f"**Utilization:** {result['beam_utilization']:.3f} ({band})")
        st.markdown(f"**Deflection:** {result.get('beam_deflection_mm', 0.0):.3f} mm")
        
        st.markdown(f"**Deflection limit:** L/{limit_ratio:.0f} = {limit_mm:.3f} mm")
        st.markdown(f"**Deflection check:** {'PASS' if ok else 'FAIL'}")
        st.markdown(f"**Cost:** {result['beam_cost_SGD']:.3f} SGD")
        st.plotly_chart(draw_beam_schematic(result), use_container_width=True)

        st.markdown("---")
        st.plotly_chart(draw_beam_deflection_plot(result, building), use_container_width=True)
        st.plotly_chart(draw_beam_sfd_plot(result, building), use_container_width=True)
        st.plotly_chart(draw_beam_bmd_plot(result, building), use_container_width=True)
    else:
        band = utilization_band_text(result["column_utilization"])
        st.caption("This panel shows the actual selected member from the current result, not just the search family.")
        st.markdown("**Member type:** Column")
        st.markdown(f"**Storey:** {result['storey']}")
        st.markdown(f"**Section:** {result['column_section']}")
        st.markdown(f"**Grade:** {result['column_grade']}")
        st.markdown(f"**Axial force:** {result['column_force_kN']:.3f} kN")
        st.markdown(f"**Stress:** {result['column_stress_MPa']:.3f} MPa")
        st.markdown(f"**Governing column check:** {result.get('column_governing_check', 'Axial stress')}")
        st.markdown(f"**Utilization:** {result['column_utilization']:.3f} ({band})")
        st.plotly_chart(draw_column_schematic(result), use_container_width=True)


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
        beam_groups = [[1], [2, 3, 4], list(range(5, num_storeys + 1))]
        column_groups = [[1, 2, 3, 4], list(range(5, num_storeys + 1))]
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
            if group == list(range(group[0], group[-1] + 1)):
                parts.append(f"{group[0]}-{group[-1]}")
            else:
                parts.append(",".join(str(x) for x in group))
    return " | ".join(parts)


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
                if a > b:
                    raise ValueError(f"Invalid range '{sp}'. Start cannot be greater than end.")
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


def build_constraints_input(num_storeys, run_mode):
    st.sidebar.markdown("---")
    st.sidebar.header("Optimization Constraints")

    u_min = st.sidebar.number_input(
        "Utilization lower bound",
        min_value=0.0,
        max_value=1.5,
        value=0.2,
        step=0.05
    )

    u_max = st.sidebar.number_input(
        "Utilization upper bound",
        min_value=0.0,
        max_value=1.5,
        value=0.7,
        step=0.05
    )

    if run_mode == "Individual-Storey Optimization":
        default_beam_groups = individual_storey_groups(num_storeys)
        default_column_groups = individual_storey_groups(num_storeys)
        default_beam_group_text = groups_to_text(default_beam_groups)
        default_column_group_text = groups_to_text(default_column_groups)

        st.sidebar.text_input(
            "Beam groups",
            value=default_beam_group_text,
            disabled=True,
            help="Locked automatically in Individual-Storey Optimization so each storey is optimized independently.",
            key=f"beam_group_text_{run_mode}_{num_storeys}"
        )

        st.sidebar.text_input(
            "Column groups",
            value=default_column_group_text,
            disabled=True,
            help="Locked automatically in Individual-Storey Optimization so each storey is optimized independently.",
            key=f"column_group_text_{run_mode}_{num_storeys}"
        )

        beam_groups = default_beam_groups
        column_groups = default_column_groups
    else:
        default_beam_groups, default_column_groups = get_group_labels(num_storeys)
        default_beam_group_text = groups_to_text(default_beam_groups)
        default_column_group_text = groups_to_text(default_column_groups)

        beam_group_text = st.sidebar.text_input(
            "Beam groups",
            value=default_beam_group_text,
            key=f"beam_group_text_{run_mode}_{num_storeys}"
        )

        column_group_text = st.sidebar.text_input(
            "Column groups",
            value=default_column_group_text,
            key=f"column_group_text_{run_mode}_{num_storeys}"
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

    # Toggle for class rules
    st.sidebar.divider()
    st.sidebar.subheader("Design Class Restrictions (Optional)")
    
    beam_class_rules_enabled = st.sidebar.checkbox(
        "Enable beam class rules",
        value=True,
        help="Check to enforce beam section class restrictions by storey"
    )

    column_class_rules_enabled = st.sidebar.checkbox(
        "Enable column class rules",
        value=True,
        help="Check to enforce column section class restrictions by storey"
    )

    beam_class_rule_storey_text = st.sidebar.text_input(
        "Beam class rule storeys",
        value="1-3",
        disabled=not beam_class_rules_enabled
    )

    beam_class_rule_allowed_text = st.sidebar.text_input(
        "Allowed beam classes for those storeys",
        value="1,2,3",
        disabled=not beam_class_rules_enabled
    )

    class_rule_storey_text = st.sidebar.text_input(
        "Column class rule storeys",
        value="1-3",
        disabled=not column_class_rules_enabled
    )

    class_rule_allowed_text = st.sidebar.text_input(
        "Allowed column classes for those storeys",
        value="1,2",
        disabled=not column_class_rules_enabled
    )

    try:
        if run_mode != "Individual-Storey Optimization":
            beam_groups = parse_group_string(beam_group_text)
            column_groups = parse_group_string(column_group_text)

        def parse_rule_storeys(rule_text):
            parsed_storeys = []
            for part in [p.strip() for p in rule_text.split(",") if p.strip()]:
                if "-" in part:
                    a, b = part.split("-")
                    a = int(a.strip())
                    b = int(b.strip())
                    if a > b:
                        raise ValueError(f"Invalid class-rule range '{part}'.")
                    parsed_storeys.extend(list(range(a, b + 1)))
                else:
                    parsed_storeys.append(int(part))
            return sorted(list(set(parsed_storeys)))

        beam_class_rule_storeys = parse_rule_storeys(beam_class_rule_storey_text)
        beam_allowed_classes = parse_class_list(beam_class_rule_allowed_text)
        class_rule_storeys = parse_rule_storeys(class_rule_storey_text)
        allowed_classes = parse_class_list(class_rule_allowed_text)

        beam_class_rules = []
        if beam_class_rules_enabled and beam_class_rule_storeys and beam_allowed_classes:
            beam_class_rules.append({
                "storeys": beam_class_rule_storeys,
                "allowed_classes": beam_allowed_classes
            })

        column_class_rules = []
        if column_class_rules_enabled and class_rule_storeys and allowed_classes:
            column_class_rules.append({
                "storeys": class_rule_storeys,
                "allowed_classes": allowed_classes
            })

    except Exception as e:
        st.sidebar.error(f"Constraint input error: {e}")
        beam_groups = default_beam_groups
        column_groups = default_column_groups
        beam_class_rules = []
        column_class_rules = []

    constraints = {
        "u_min": u_min,
        "u_max": u_max,
        "beam_groups": beam_groups,
        "column_groups": column_groups,
        "min_grade": min_grade,
        "max_grade": max_grade,
        "allowed_beam_shapes": allowed_beam_shapes,
        "allowed_column_shapes": allowed_column_shapes,
        "beam_class_rules": beam_class_rules,
        "column_class_rules": column_class_rules
    }

    return constraints, beam_class_rules_enabled, column_class_rules_enabled


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

    governing_basis = st.sidebar.selectbox(
        "Governing criterion",
        ["utilization", "stress", "moment", "deflection"],
        index=0
    )

    candidate_pool = st.sidebar.number_input(
        "Candidate pool size per shape",
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
                "height": 1.5,
                "dead_load": 1.5,
                "live_load": 1.5,
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

    constraints, beam_class_rules_enabled, column_class_rules_enabled = build_constraints_input(num_storeys, run_mode)

    st.sidebar.markdown("---")
    run_clicked = st.sidebar.button("Run Current Mode", use_container_width=True)
    clear_clicked = st.sidebar.button("Clear Saved Results", use_container_width=True)

    return {
        "num_storeys": num_storeys,
        "span": span,
        "design_standard": design_standard,
        "storeys": rows,
        "run_mode": run_mode,
        "governing_basis": governing_basis,
        "candidate_pool": candidate_pool,
        "constraints": constraints,
        "beam_class_rules_enabled": beam_class_rules_enabled,
        "column_class_rules_enabled": column_class_rules_enabled,
        "run_clicked": run_clicked,
        "clear_clicked": clear_clicked,
    }


def show_optimization_settings(input_data):
    st.subheader("Optimization Settings")
    st.markdown(f"**Mode:** {input_data['run_mode']}")
    st.markdown(
        f"**Beam shapes searched:** {', '.join(input_data['constraints']['allowed_beam_shapes'])}"
    )
    st.markdown(
        f"**Column shapes searched:** {', '.join(input_data['constraints']['allowed_column_shapes'])}"
    )
    st.markdown(f"**Utilization lower bound:** {input_data['constraints']['u_min']:.2f}")
    st.markdown(f"**Utilization upper bound:** {input_data['constraints']['u_max']:.2f}")
    st.markdown(f"**Candidate pool size per shape:** {int(input_data['candidate_pool'])}")
    st.markdown(
        f"**Steel grade range:** {input_data['constraints']['min_grade']} to {input_data['constraints']['max_grade']}"
    )
    st.markdown(
        f"**Beam groups applied:** {groups_to_text(input_data['constraints']['beam_groups'])}"
    )
    st.markdown(
        f"**Column groups applied:** {groups_to_text(input_data['constraints']['column_groups'])}"
    )
    if input_data["constraints"]["beam_class_rules"]:
        beam_rules_text = "; ".join(
            f"storeys {groups_to_text([rule['storeys']])}: classes {', '.join(str(c) for c in rule['allowed_classes'])}"
            for rule in input_data["constraints"]["beam_class_rules"]
        )
        st.markdown(f"**Beam class rules:** {beam_rules_text}")
    if input_data["constraints"]["column_class_rules"]:
        column_rules_text = "; ".join(
            f"storeys {groups_to_text([rule['storeys']])}: classes {', '.join(str(c) for c in rule['allowed_classes'])}"
            for rule in input_data["constraints"]["column_class_rules"]
        )
        st.markdown(f"**Column class rules:** {column_rules_text}")


def show_optimization_summary(input_data, optimization_result):
    if optimization_result is None:
        return

    st.subheader("Optimization Summary")

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
                    f"- **Beam Group {i} ({group_text})**: {d['section']} | {d['grade']} | Util: {d['max_utilization']:.3f}"
                )

        if optimization_result.get("best_column_designs"):
            st.markdown("**Optimized Column Designs**")
            for i, d in enumerate(optimization_result["best_column_designs"], start=1):
                group_text = format_storey_group(column_groups[i - 1])
                st.markdown(
                    f"- **Column Group {i} ({group_text})**: {d['section']} | {d['grade']} | Util: {d['max_utilization']:.3f}"
                )

        if optimization_result.get("meta"):
            st.markdown(
                f"**Combinations checked:** {optimization_result['meta'].get('checked_combinations', 0)}"
            )
            st.markdown(
                f"**Feasible combinations:** {optimization_result['meta'].get('feasible_combinations', 0)}"
            )

    elif mode == "Individual-Storey Optimization":
        if optimization_result.get("best_beam_designs"):
            st.markdown("**Optimized Beam Designs by Storey**")
            for i, d in enumerate(optimization_result["best_beam_designs"], start=1):
                st.markdown(f"- **Storey {i} Beam**: {d['section']} | {d['grade']} | Util: {d['max_utilization']:.3f}")

        if optimization_result.get("best_column_designs"):
            st.markdown("**Optimized Column Designs by Storey**")
            for i, d in enumerate(optimization_result["best_column_designs"], start=1):
                st.markdown(f"- **Storey {i} Column**: {d['section']} | {d['grade']} | Util: {d['max_utilization']:.3f}")

    storage = optimization_result.get("storage")
    if storage:
        st.markdown(f"**Saved Excel output:** `{storage['excel_path']}`")
        st.markdown(f"**Saved structured results file:** `{storage['results_path']}` (run ID {storage['run_id']})")


def main():
    st.set_page_config(page_title="CE3204 Interactive Frame Viewer", layout="wide")
    initialize_app_state()

    default_data = load_module1_input("input_module1.json")
    all_sections = get_cached_section_names()
    all_grades = get_cached_material_grades()
    all_codes = get_cached_design_standard_codes()

    input_data = build_sidebar_input(default_data, all_sections, all_grades, all_codes)

    if input_data["clear_clicked"]:
        clear_computed_payload()

    if st.session_state["last_mode"] != input_data["run_mode"]:
        st.session_state["last_mode"] = input_data["run_mode"]

    min_grade_val = int(input_data["constraints"]["min_grade"].replace("S", ""))
    max_grade_val = int(input_data["constraints"]["max_grade"].replace("S", ""))

    if min_grade_val > max_grade_val:
        st.error("Invalid grade range: minimum steel grade is higher than maximum steel grade.")
        return

    st.title("CE3204 Interactive Frame Viewer")

    try:
        building, design = build_building_from_module1(input_data)
    except Exception as e:
        st.error(f"Input/build error: {e}")
        return

    current_signature = build_run_signature(input_data)

    if input_data["run_clicked"]:
        try:
            with st.spinner(f"Running {input_data['run_mode'].lower()}..."):
                if input_data["run_mode"] == "Analysis":
                    payload = run_analysis_service(
                        building,
                        design,
                        governing_basis=input_data["governing_basis"],
                    )
                else:
                    payload = run_optimization_service(building, design, input_data)

                if payload.get("summary") is None:
                    clear_computed_payload()
                    st.session_state["last_error"] = (
                        "No feasible grouped optimization design found."
                        if input_data["run_mode"] == "Grouped Optimization"
                        else "No feasible individual-storey optimization design found."
                    )
                else:
                    st.session_state["computed_payload"] = payload
                    st.session_state["last_run_signature"] = current_signature
                    st.session_state["last_error"] = None

        except Exception as e:
            clear_computed_payload()
            st.session_state["last_error"] = f"Analysis/optimization error: {e}"

    payload = st.session_state.get("computed_payload")

    if st.session_state.get("last_error"):
        st.error(st.session_state["last_error"])

    if payload is None:
        st.info("Set your inputs, then click 'Run Current Mode'. Saved results stay on screen until you run again or clear them.")
        show_optimization_settings(input_data)
        return

    if st.session_state.get("last_run_signature") != current_signature:
        st.warning("Displayed results are from the last run. Click 'Run Current Mode' to refresh them with your latest inputs.")

    building = payload["building"]
    results = payload["results"]
    summary = payload["summary"]
    optimization_result = payload if input_data["run_mode"] != "Analysis" else None

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Cost (SGD)", f"{summary['total_cost_SGD']:.3f}")
    c2.metric(summary["governing_label"], f"{summary['governing_value']:.3f} {summary['governing_unit']}")
    c3.metric("Governing Member", f"{summary['governing_member_type']} @ Storey {summary['governing_storey']}")

    st.markdown("---")

    if optimization_result is not None:
        show_optimization_settings(input_data)
        show_optimization_summary(input_data, optimization_result)
        st.markdown("---")

    member_options = build_member_options(results)
    selected_text = st.selectbox("Select member to inspect", member_options)

    selected_member_type, selected_storey = parse_selected_member(selected_text)
    selected_result = get_selected_result(results, selected_member_type, selected_storey)

    left, right = st.columns([2.3, 1])

    with left:
        fig = create_interactive_frame(
            building,
            results,
            selected_member_type,
            selected_storey,
            input_data["governing_basis"])
        st.plotly_chart(fig, use_container_width=True)

    with right:
        show_utilization_legend()
        st.markdown("---")
        show_member_details(selected_result, selected_member_type, building)

        st.subheader("Governing Member")
        st.markdown(f"**Type:** {summary['governing_member_type']}")
        st.markdown(f"**Storey:** {summary['governing_storey']}")
        st.markdown(f"**Utilization:** {summary['max_utilization']:.3f}")

    if optimization_result is not None and optimization_result.get("storage"):
        file_path = optimization_result["storage"]["excel_path"]
    else:
        os.makedirs("outputs", exist_ok=True)
        file_path = export_results_to_excel(results, summary)

    with open(file_path, "rb") as f:
        st.download_button(
            label="Download Excel Results",
            data=f.read(),
            file_name=Path(file_path).name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


if __name__ == "__main__":
    main()
