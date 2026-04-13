from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "outputs"


def get_member_color(utilization):
    if utilization < 0.6:
        return "green"
    elif utilization < 0.8:
        return "orange"
    else:
        return "red"


def plot_frame(building, results, summary, filename="frame_plot.png"):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = OUTPUT_DIR / filename

    results = sorted(results, key=lambda x: x["storey"])

    fig, ax = plt.subplots(figsize=(12, 10))

    x_left = 0
    x_right = building.span
    current_y = 0

    governing_type = summary.get("governing_member_type")
    governing_storey = summary.get("governing_storey")
    governing_util = summary.get("max_utilization")

    for r in results:
        storey_height = r["height_m"]
        next_y = current_y + storey_height

        beam_color = get_member_color(r["beam_utilization"])
        col_color = get_member_color(r["column_utilization"])

        is_governing_beam = (
            governing_type == "Beam" and r["storey"] == governing_storey
        )
        is_governing_column = (
            governing_type == "Column" and r["storey"] == governing_storey
        )

        # Draw columns
        ax.plot([x_left, x_left], [current_y, next_y], linewidth=4, color=col_color, zorder=2)
        ax.plot([x_right, x_right], [current_y, next_y], linewidth=4, color=col_color, zorder=2)

        # Draw beam
        ax.plot([x_left, x_right], [next_y, next_y], linewidth=4, color=beam_color, zorder=2)

        # Beam label
        beam_label = f"{r['beam_section']}\nU={r['beam_utilization']:.3f}"
        if is_governing_beam:
            beam_label += "\n★ GOV"

        ax.text(
            x_right / 2,
            next_y + 0.12,
            beam_label,
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold" if is_governing_beam else "normal"
        )

        # Column labels
        col_label = f"{r['column_section']}\nU={r['column_utilization']:.3f}"
        if is_governing_column:
            col_label += "\n★ GOV"

        ax.text(
            x_left - 0.4,
            (current_y + next_y) / 2,
            col_label,
            ha="right",
            va="center",
            fontsize=8,
            fontweight="bold" if is_governing_column else "normal"
        )

        ax.text(
            x_right + 0.4,
            (current_y + next_y) / 2,
            col_label,
            ha="left",
            va="center",
            fontsize=8,
            fontweight="bold" if is_governing_column else "normal"
        )

        current_y = next_y

    # Legend outside plot
    legend_elements = [
        Line2D([0], [0], color="green", lw=4, label="U < 0.6"),
        Line2D([0], [0], color="orange", lw=4, label="0.6 ≤ U < 0.8"),
        Line2D([0], [0], color="red", lw=4, label="U ≥ 0.8"),
    ]
    ax.legend(
        handles=legend_elements,
        loc="upper left",
        bbox_to_anchor=(1.02, 1.0),
        borderaxespad=0.0,
        fontsize=9,
        frameon=True,
        title="Utilization bands"
    )

    # Governing member info box outside plot
    gov_text = (
        f"Governing member\n"
        f"Type: {governing_type}\n"
        f"Storey: {governing_storey}\n"
        f"U = {governing_util:.3f}"
    )

    ax.text(
        1.02, 0.72,
        gov_text,
        transform=ax.transAxes,
        fontsize=9,
        va="top",
        ha="left",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="black")
    )

    ax.set_title("Steel Frame Utilization Plot")
    ax.set_xlabel("Span (m)")
    ax.set_ylabel("Height (m)")
    ax.set_xlim(-2.0, building.span + 2.0)
    ax.set_ylim(0, current_y + 1)
    ax.set_aspect("equal")
    ax.grid(True, linestyle="--", alpha=0.4)

    plt.subplots_adjust(right=0.72)
    plt.savefig(filepath, dpi=300, bbox_inches="tight")
    plt.close()

    return filepath