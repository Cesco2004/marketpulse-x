"""Chart generator: creates professional financial charts for tweet images."""

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# Color palette
COLORS = {
    "bg": "#0d1117",
    "card": "#161b22",
    "border": "#30363d",
    "text": "#e6edf3",
    "text_dim": "#8b949e",
    "green": "#3fb950",
    "green_soft": "#238636",
    "red": "#f85149",
    "red_soft": "#da3633",
    "blue": "#58a6ff",
    "yellow": "#d29922",
    "purple": "#bc8cff",
    "cyan": "#39d2c0",
}


def generate_chart(chart_type, data, title, output_path, chart_config=None):
    """Generate a professional chart image for tweet attachment."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        import matplotlib.ticker as mticker
    except ImportError:
        logger.error("matplotlib not installed")
        return None

    cfg = chart_config or {}
    watermark = cfg.get("watermark_text", "@MarketPulseBot")

    # Global style
    plt.rcParams.update({
        "figure.facecolor": COLORS["bg"],
        "axes.facecolor": COLORS["bg"],
        "axes.edgecolor": COLORS["border"],
        "axes.labelcolor": COLORS["text_dim"],
        "text.color": COLORS["text"],
        "xtick.color": COLORS["text_dim"],
        "ytick.color": COLORS["text_dim"],
        "grid.color": COLORS["border"],
        "grid.alpha": 0.4,
        "grid.linestyle": "--",
        "grid.linewidth": 0.5,
        "font.family": "monospace",
        "font.size": 10,
    })

    fig, ax = plt.subplots(figsize=(12, 6.28), dpi=100)

    try:
        if chart_type == "line":
            _draw_line_chart(ax, data)
        elif chart_type == "bar":
            _draw_bar_chart(ax, data)
        elif chart_type == "odds":
            _draw_odds_chart(ax, data)
        elif chart_type == "pie":
            _draw_pie_chart(ax, fig, data)
        elif chart_type == "comparison":
            _draw_comparison_chart(ax, data)
        else:
            _draw_line_chart(ax, data)

        # Title - top left, bold, large
        ax.text(0.0, 1.06, title.upper(), transform=ax.transAxes,
                fontsize=13, fontweight="bold", color=COLORS["text"],
                fontfamily="monospace")

        # Watermark - bottom right, very subtle
        fig.text(0.97, 0.01, watermark, fontsize=7, color=COLORS["text_dim"],
                 alpha=0.3, ha="right", va="bottom", fontfamily="monospace")

        # Timestamp - bottom left
        fig.text(0.03, 0.01, datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                 fontsize=7, color=COLORS["text_dim"], alpha=0.3,
                 ha="left", va="bottom", fontfamily="monospace")

        # Clean spines
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(COLORS["border"])
        ax.spines["bottom"].set_color(COLORS["border"])
        ax.spines["left"].set_linewidth(0.5)
        ax.spines["bottom"].set_linewidth(0.5)

        plt.tight_layout(rect=[0.01, 0.03, 0.99, 0.93])

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, bbox_inches="tight", facecolor=COLORS["bg"],
                    edgecolor="none", pad_inches=0.3)
        plt.close(fig)

        logger.info(f"Chart saved: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Chart generation error: {e}")
        plt.close(fig)
        return None


def _draw_line_chart(ax, data):
    """Price/odds line chart with gradient fill."""
    values = data.get("values", [])
    labels = data.get("labels", [])
    label = data.get("label", "Price")

    if not values:
        return

    x = range(len(values))

    # Direction color
    is_up = values[-1] >= values[0] if len(values) >= 2 else True
    color = COLORS["green"] if is_up else COLORS["red"]
    color_soft = COLORS["green_soft"] if is_up else COLORS["red_soft"]

    # Main line
    ax.plot(x, values, color=color, linewidth=2.5, zorder=5, solid_capstyle="round")

    # Gradient fill
    ax.fill_between(x, values, min(values) - (max(values) - min(values)) * 0.1,
                     alpha=0.08, color=color)

    # Start/end dots
    ax.scatter([0], [values[0]], color=COLORS["text_dim"], s=25, zorder=6, edgecolors="none")
    ax.scatter([len(values) - 1], [values[-1]], color=color, s=50, zorder=6, edgecolors="none")

    # End value label with background box
    change_pct = ((values[-1] - values[0]) / values[0] * 100) if values[0] != 0 else 0
    sign = "+" if change_pct >= 0 else ""
    end_label = f" {values[-1]:,.2f}  ({sign}{change_pct:.1f}%) "

    ax.annotate(
        end_label, (len(values) - 1, values[-1]),
        textcoords="offset points", xytext=(12, 0),
        fontsize=11, fontweight="bold", color=color,
        fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.3", facecolor=COLORS["card"],
                  edgecolor=color, alpha=0.9, linewidth=1),
        zorder=10,
    )

    # Start value (subtle)
    ax.annotate(
        f"{values[0]:,.2f}", (0, values[0]),
        textcoords="offset points", xytext=(-8, 12),
        fontsize=8, color=COLORS["text_dim"], ha="right",
        fontfamily="monospace",
    )

    # Y-axis: zoom into data range (don't start from 0)
    data_range = max(values) - min(values)
    padding = data_range * 0.25 if data_range > 0 else abs(values[0]) * 0.02
    ax.set_ylim(min(values) - padding, max(values) + padding)

    # X-axis labels
    if labels:
        step = max(1, len(labels) // 5)
        ticks = list(range(0, len(labels), step))
        ax.set_xticks(ticks)
        ax.set_xticklabels([labels[i][-5:] if len(labels[i]) > 5 else labels[i] for i in ticks],
                           fontsize=8, rotation=0)
    else:
        ax.set_xticks([])

    ax.set_ylabel(label, fontsize=9, labelpad=10)
    ax.grid(True, axis="y")
    ax.grid(False, axis="x")
    ax.tick_params(axis="both", length=0)


def _draw_bar_chart(ax, data):
    """Horizontal bar chart for top movers."""
    names = data.get("names", [])
    values = data.get("values", [])

    if not names or not values:
        return

    # Sort by absolute value
    paired = sorted(zip(names, values), key=lambda x: abs(x[1]), reverse=True)
    names, values = zip(*paired)

    colors = [COLORS["green"] if v >= 0 else COLORS["red"] for v in values]

    bars = ax.barh(names, values, color=colors, height=0.55, edgecolor="none",
                   alpha=0.85, zorder=3)

    # Value labels
    for bar, val in zip(bars, values):
        label = f"{val:+.1f}%" if data.get("is_percent") else f"{val:,.0f}"
        x_pos = bar.get_width()
        offset = 0.15 * (1 if x_pos >= 0 else -1)
        ha = "left" if x_pos >= 0 else "right"
        color = COLORS["green"] if val >= 0 else COLORS["red"]
        ax.text(x_pos + offset, bar.get_y() + bar.get_height() / 2,
                f" {label} ", va="center", ha=ha, fontsize=10, fontweight="bold",
                color=color, fontfamily="monospace",
                bbox=dict(boxstyle="round,pad=0.2", facecolor=COLORS["card"],
                          edgecolor="none", alpha=0.8))

    ax.axvline(x=0, color=COLORS["border"], linewidth=0.8, zorder=1)
    ax.set_xlabel(data.get("xlabel", "Change %"), fontsize=9)
    ax.grid(True, axis="x")
    ax.grid(False, axis="y")
    ax.invert_yaxis()
    ax.tick_params(axis="both", length=0)


def _draw_odds_chart(ax, data):
    """Polymarket odds chart."""
    yes_values = data.get("yes_values", [])
    no_values = data.get("no_values", [])
    labels = data.get("labels", [])

    if not yes_values:
        return

    x = range(len(yes_values))

    # Yes line
    ax.plot(x, yes_values, color=COLORS["green"], linewidth=2.5, label="Yes", zorder=5)
    ax.fill_between(x, yes_values, alpha=0.06, color=COLORS["green"])

    # No line
    if no_values:
        ax.plot(x, no_values, color=COLORS["red"], linewidth=2, label="No",
                linestyle="--", alpha=0.7, zorder=4)

    # Current value
    if yes_values:
        ax.annotate(
            f" {yes_values[-1]:.0f}% ", (len(yes_values) - 1, yes_values[-1]),
            textcoords="offset points", xytext=(12, 0),
            fontsize=12, fontweight="bold", color=COLORS["green"],
            fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=COLORS["card"],
                      edgecolor=COLORS["green"], alpha=0.9, linewidth=1),
            zorder=10,
        )

    ax.set_ylabel("Probability", fontsize=9, labelpad=10)
    ax.set_ylim(-2, 102)
    ax.yaxis.set_major_formatter(lambda x, _: f"{x:.0f}%")

    # Horizontal reference lines
    for level in [25, 50, 75]:
        ax.axhline(y=level, color=COLORS["border"], linewidth=0.5, linestyle=":", alpha=0.5)

    ax.legend(loc="upper left", fontsize=9, framealpha=0.5,
              facecolor=COLORS["card"], edgecolor=COLORS["border"])
    ax.grid(False)
    ax.tick_params(axis="both", length=0)


def _draw_pie_chart(ax, fig, data):
    """Market dominance donut chart."""
    labels = data.get("labels", [])
    values = data.get("values", [])
    colors = data.get("colors", [COLORS["yellow"], COLORS["blue"], COLORS["text_dim"]])

    if not labels or not values:
        return

    wedges, texts, autotexts = ax.pie(
        values, labels=None, colors=colors[:len(values)],
        autopct="%1.1f%%", startangle=90, pctdistance=0.75,
        wedgeprops=dict(width=0.4, edgecolor=COLORS["bg"], linewidth=2),
        textprops={"color": COLORS["text"], "fontsize": 11, "fontweight": "bold",
                   "fontfamily": "monospace"},
    )

    # Legend instead of labels on pie
    ax.legend(wedges, labels, loc="center left", bbox_to_anchor=(-0.15, 0.5),
              fontsize=10, frameon=False,
              labelcolor=COLORS["text"])

    for t in autotexts:
        t.set_fontweight("bold")


def _draw_comparison_chart(ax, data):
    """Side-by-side comparison bars."""
    categories = data.get("categories", [])
    values_a = data.get("values_a", [])
    values_b = data.get("values_b", [])
    label_a = data.get("label_a", "A")
    label_b = data.get("label_b", "B")

    if not categories:
        return

    import numpy as np
    x = np.arange(len(categories))
    width = 0.32

    ax.bar(x - width / 2, values_a, width, label=label_a,
           color=COLORS["blue"], alpha=0.85, edgecolor="none", zorder=3)
    ax.bar(x + width / 2, values_b, width, label=label_b,
           color=COLORS["purple"], alpha=0.85, edgecolor="none", zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=9)
    ax.legend(fontsize=9, framealpha=0.5, facecolor=COLORS["card"],
              edgecolor=COLORS["border"])
    ax.grid(True, axis="y")
    ax.grid(False, axis="x")
    ax.tick_params(axis="both", length=0)
