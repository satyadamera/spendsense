"""Matplotlib charts rendered to PNG bytes for the Word and PowerPoint reports."""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

INK = "#1f2933"
MUTED = "#6b7280"
GRID = "#e5e7eb"
SPEND = "#d9480f"
INCOME = "#2b8a3e"
BAR = "#3b5bdb"


def _inr_axis(x, _pos):
    if x >= 1e5:
        return f"₹{x / 1e5:.1f}L"
    if x >= 1e3:
        return f"₹{x / 1e3:.0f}k"
    return f"₹{x:.0f}"


def _style(ax):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.set_axisbelow(True)


def _to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def category_chart(by_category: list[dict], width: float = 7.0) -> bytes:
    rows = by_category[:10][::-1]
    fig, ax = plt.subplots(figsize=(width, 0.42 * len(rows) + 0.8))
    labels = [r["category"] for r in rows]
    values = [r["amount"] for r in rows]
    bars = ax.barh(labels, values, color=BAR, height=0.6)
    for bar, r in zip(bars, rows):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f"  {r['share']}%",
                va="center", fontsize=9, color=MUTED)
    ax.xaxis.set_major_formatter(FuncFormatter(_inr_axis))
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_xlim(0, max(values) * 1.15 if values else 1)
    ax.tick_params(axis="y", colors=INK, labelsize=10)
    _style(ax)
    return _to_png(fig)


def monthly_chart(monthly: list[dict], width: float = 7.0) -> bytes:
    fig, ax = plt.subplots(figsize=(width, 3.2))
    months = [m.get("label", m["month"]) for m in monthly]
    x = range(len(months))
    w = 0.38
    ax.bar([i - w / 2 for i in x], [m["income"] for m in monthly], w, label="Income", color=INCOME)
    ax.bar([i + w / 2 for i in x], [m["spend"] for m in monthly], w, label="Spending", color=SPEND)
    ax.set_xticks(list(x), months)
    ax.yaxis.set_major_formatter(FuncFormatter(_inr_axis))
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.legend(frameon=False, fontsize=9, loc="lower left", bbox_to_anchor=(0, 1.0), ncols=2)
    _style(ax)
    return _to_png(fig)
