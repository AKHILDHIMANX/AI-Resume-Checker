"""
Chart generation for the results dashboard.

Uses matplotlib with the non-interactive ``Agg`` backend so the server needs no
display. Each chart is written as a PNG and served as a static file, which
keeps the templates free of any JavaScript charting library.

Where the PNG goes depends on what the host allows:

* **File mode** (default) - the chart is written to ``public/static/img/charts/``
  and returned as a ``/static/...`` URL. Old files are pruned on every run.
* **Inline mode** (``CHART_MODE=inline``) - the chart is returned as a
  ``data:image/png;base64,...`` URI and nothing touches the filesystem.

Inline mode exists for serverless hosts, where the project directory is
read-only and every write must go to a per-instance temporary directory. A PNG
written to such a directory cannot be served reliably, because the follow-up
request for the image may be handled by a different instance and find nothing.
Inlining removes that dependency entirely, and ``<img src>`` accepts a data URI
unchanged, so no template needs to know which mode is active.

Charts produced
---------------
* ``scores``      - horizontal bar chart of every score
* ``radar``       - spider chart of the four components plus overall
* ``ats_radar``   - spider chart of the eight ATS readability checks
* ``skills``      - technical skills per category
* ``job_match``   - matched vs missing skills for the selected role
* ``keywords``    - top TF-IDF keyword frequencies
* ``role_fit``    - resume-to-role similarity across all roles
"""

from __future__ import annotations

import base64
import io
import os
import tempfile
import uuid
from typing import Dict, List, Optional


def _matplotlib_config_dir() -> None:
    """
    Point matplotlib at a writable directory before it is imported.

    Matplotlib writes a font cache under ``~/.cache/matplotlib`` the first time
    it draws. A serverless host commonly has a read-only home directory, and
    matplotlib then falls back to a temporary directory of its own while
    warning on every import. Choosing the location up front keeps that noise out
    of the logs, keeps the cache reusable across invocations when it can be, and
    never fails the way a read-only ``~`` would.
    """
    if os.environ.get("MPLCONFIGDIR"):
        return  # already chosen explicitly; do not second-guess the operator
    for candidate in (
        os.path.join(os.path.expanduser("~"), ".cache", "matplotlib"),
        os.path.join(tempfile.gettempdir(), "matplotlib"),
    ):
        try:
            os.makedirs(candidate, exist_ok=True)
            probe = os.path.join(candidate, ".write-probe")
            with open(probe, "w", encoding="utf-8") as handle:
                handle.write("ok")
            os.remove(probe)
        except OSError:
            continue
        os.environ["MPLCONFIGDIR"] = candidate
        return
    # Nothing is writable. matplotlib will pick its own fallback and warn, but
    # failing here would mean failing to import the chart module at all.
    os.environ["MPLCONFIGDIR"] = tempfile.gettempdir()


_matplotlib_config_dir()

import matplotlib  # noqa: E402  (must follow _matplotlib_config_dir)

matplotlib.use("Agg")  # headless backend - must be set before pyplot import
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")  # text exports written by app.py
STATIC_CHART_DIR = os.path.join(
    PROJECT_ROOT, "public", "static", "img", "charts"
)  # must match app.static_folder so the returned URL resolves

# "file" (default) or "inline". Any unrecognised value falls back to "file".
#
# The default is chosen rather than fixed: Vercel mounts the project read-only
# and gives each instance its own temporary directory, so a PNG written under
# public/static/img/charts/ would be reachable only from the instance that
# wrote it, and the request for that image may be handled by another. Detecting
# the platform means the safe mode applies on the first deploy without any
# environment variable having to be configured, while CHART_MODE still lets a
# local run or a different host choose explicitly.
_CHART_MODE_DEFAULT = "inline" if os.environ.get("VERCEL") else "file"
CHART_MODE = (os.environ.get("CHART_MODE") or _CHART_MODE_DEFAULT).strip().lower()
INLINE_CHARTS = CHART_MODE == "inline"

# Restrained palette - no gradients, no 3D, matches the UI.
PRIMARY = "#2f6fed"
SECONDARY = "#20a37a"
ACCENT = "#f0a202"
MUTED = "#94a3b8"
DANGER = "#e05252"
BG = "#ffffff"
GRID = "#e6eaf0"
TEXT = "#1f2937"


def _ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _new_figure(width: float = 8.0, height: float = 4.0):
    fig, ax = plt.subplots(figsize=(width, height), dpi=110)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(GRID)
    ax.tick_params(colors=TEXT, labelsize=9)
    return fig, ax


def _save(fig, name: str) -> Optional[str]:
    """Render the figure and return a value usable directly as an ``img src``.

    Returns either a ``data:`` URI (inline mode) or a ``/static/...`` URL.
    Never raises: a chart problem must not invalidate an otherwise correct
    analysis, so a failure simply omits that chart.
    """
    try:
        if INLINE_CHARTS:
            buffer = io.BytesIO()
            fig.savefig(buffer, format="png", facecolor=BG, bbox_inches="tight")
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            return f"data:image/png;base64,{encoded}"

        _ensure_dir(STATIC_CHART_DIR)
        filename = f"{name}_{uuid.uuid4().hex[:8]}.png"
        fig.savefig(
            os.path.join(STATIC_CHART_DIR, filename),
            facecolor=BG,
            bbox_inches="tight",
        )
        return f"/static/img/charts/{filename}"
    except Exception:  # noqa: BLE001 - never break analysis over a chart
        return None
    finally:
        plt.close(fig)


def _color_for(value: float) -> str:
    if value >= 80:
        return SECONDARY
    if value >= 60:
        return PRIMARY
    if value >= 40:
        return ACCENT
    return DANGER


def _radar(
    labels: List[str],
    values: List[float],
    title: str,
    name: str,
    rings: int = 4,
):
    """
    Draw a spider (radar) chart and return the saved figure path.

    A radar chart is used here because it compresses several independent
    0-100 measurements into one shape: the area of the polygon is easy to read
    as "overall balance" and a dent in one axis is immediately visible.
    """
    count = len(labels)
    if count < 3:
        return None

    angles = np.linspace(0, 2 * np.pi, count, endpoint=False).tolist()
    angles_closed = angles + angles[:1]
    values_closed = list(values) + [values[0]]

    fig, ax = plt.subplots(figsize=(6.4, 5.2), dpi=110, subplot_kw={"polar": True})
    fig.patch.set_facecolor(BG)

    # Concentric guide rings.
    for level in range(1, rings + 1):
        ax.plot(
            angles_closed,
            [100 / rings * level] * (count + 1),
            color=GRID,
            linewidth=0.9,
            zorder=1,
        )

    # Filled profile polygon.
    ax.fill(angles_closed, values_closed, color=PRIMARY, alpha=0.20, zorder=2)
    ax.plot(
        angles_closed,
        values_closed,
        color=PRIMARY,
        linewidth=2.2,
        marker="o",
        markersize=5.5,
        markerfacecolor="#ffffff",
        markeredgewidth=2,
        markeredgecolor=PRIMARY,
        zorder=3,
    )

    # Value callouts on every vertex.
    for angle, value in zip(angles, values):
        ax.annotate(
            f"{value:.0f}",
            xy=(angle, value),
            xytext=(0, 13),
            textcoords="offset points",
            ha="center",
            fontsize=9.5,
            fontweight="bold",
            color=TEXT,
            zorder=4,
        )

    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=9.5, color=TEXT, fontweight="bold")
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75, 100])
    ax.set_yticklabels(["25", "50", "75", "100"], fontsize=7.5, color=MUTED)
    ax.set_rlabel_position(90)
    ax.tick_params(axis="x", pad=14)
    ax.spines["polar"].set_color(GRID)
    ax.grid(False)
    ax.set_facecolor(BG)

    ax.set_title(title, color=TEXT, fontsize=12, fontweight="bold", pad=26, loc="left")
    return _save(fig, name)


# --------------------------------------------------------------------------
# Individual charts
# --------------------------------------------------------------------------
def score_distribution_chart(score_report) -> Optional[str]:
    """Horizontal bars for Overall / Structure / Content / Skills / ATS."""
    items = [(component.label.replace(" Score", ""), component.score)
             for component in score_report.components]
    items.insert(0, ("Overall", score_report.overall))

    labels = [item[0] for item in items][::-1]
    values = [item[1] for item in items][::-1]
    colors = [_color_for(value) for value in values]

    fig, ax = _new_figure(7.6, 0.62 * len(labels) + 1.4)
    bars = ax.barh(labels, values, color=colors, height=0.58)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Score out of 100", color=TEXT, fontsize=9)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)

    for bar, value in zip(bars, values):
        ax.text(
            value + 1.5,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.0f}",
            va="center",
            fontsize=9,
            color=TEXT,
        )

    ax.set_title(
        "Score distribution",
        color=TEXT,
        fontsize=11,
        loc="left",
        pad=10,
    )
    return _save(fig, "scores")


def skill_category_chart(profile) -> Optional[str]:
    """How many technical skills were detected per category."""
    counts = profile.category_counts
    if not counts:
        return None

    labels = list(counts.keys())[::-1]
    values = [counts[key] for key in labels]

    fig, ax = _new_figure(7.6, 0.55 * len(labels) + 1.3)
    ax.barh(labels, values, color=PRIMARY, height=0.6)
    ax.set_xlabel("Skills detected", color=TEXT, fontsize=9)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title("Technical skills by category", color=TEXT, fontsize=11, loc="left", pad=10)

    for index, value in enumerate(values):
        ax.text(value + 0.12, index, str(value), va="center", fontsize=9, color=TEXT)

    return _save(fig, "skills")


def job_match_chart(job_result) -> Optional[str]:
    """Matched / missing skills for the selected role, grouped by importance."""
    if job_result is None:
        return None

    groups = [
        ("Core matched", job_result.matched_core, SECONDARY),
        ("Preferred matched", job_result.matched_preferred, PRIMARY),
        ("Bonus matched", job_result.matched_bonus, MUTED),
        ("Core missing", job_result.missing_core, DANGER),
        ("Preferred missing", job_result.missing_preferred, ACCENT),
    ]
    groups = [item for item in groups if item[1]]
    if not groups:
        return None

    labels: List[str] = []
    values: List[int] = []
    colors: List[str] = []
    for name, skills, color in groups:
        labels.append(name)
        values.append(len(skills))
        colors.append(color)
    labels, values, colors = labels[::-1], values[::-1], colors[::-1]

    fig, ax = _new_figure(7.6, 0.62 * len(labels) + 1.3)
    ax.barh(labels, values, color=colors, height=0.6)
    ax.set_xlabel("Number of skills", color=TEXT, fontsize=9)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(
        f"Role match breakdown - {job_result.role}",
        color=TEXT,
        fontsize=11,
        loc="left",
        pad=10,
    )

    for index, value in enumerate(values):
        ax.text(value + 0.12, index, str(value), va="center", fontsize=9, color=TEXT)

    return _save(fig, "job_match")


def keyword_frequency_chart(profile, top_n: int = 12) -> Optional[str]:
    """Top TF-IDF terms as a simple frequency bar chart."""
    terms = profile.frequent_terms[:top_n]
    if not terms:
        return None

    labels = [item["term"] for item in terms][::-1]
    values = [item["count"] for item in labels[::-1]]

    fig, ax = _new_figure(7.6, 0.36 * len(labels) + 1.5)
    ax.barh(labels, values, color=PRIMARY, height=0.6)
    ax.set_xlabel("Occurrences in resume", color=TEXT, fontsize=9)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title("Most frequent terms", color=TEXT, fontsize=11, loc="left", pad=10)

    return _save(fig, "keywords")


def role_fit_chart(role_overview: List[Dict]) -> Optional[str]:
    """Similarity against every role in the dataset."""
    if not role_overview:
        return None

    items = role_overview[::-1]
    labels = [item["role"] for item in items]
    values = [item["score"] for item in items]
    colors = [_color_for(value) for value in values]

    fig, ax = _new_figure(7.6, 0.5 * len(labels) + 1.5)
    ax.barh(labels, values, color=colors, height=0.6)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Resume-to-role similarity (0-100)", color=TEXT, fontsize=9)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(
        "Similarity across all supported roles",
        color=TEXT,
        fontsize=11,
        loc="left",
        pad=10,
    )

    for index, value in enumerate(values):
        ax.text(value + 1.2, index, f"{value:.0f}", va="center", fontsize=9, color=TEXT)

    return _save(fig, "role_fit")


def section_coverage_chart(resume) -> Optional[str]:
    """Detected vs missing resume sections."""
    found = set(resume.sections_found)
    labels, values, colors = [], [], []
    for key, label in SECTION_ORDER_LABELS:
        labels.append(label)
        if key in found:
            values.append(1)
            colors.append(SECONDARY)
        else:
            values.append(0)
            colors.append(GRID)
    labels, values, colors = labels[::-1], values[::-1], colors[::-1]

    fig, ax = _new_figure(7.6, 0.42 * len(labels) + 1.3)
    ax.barh(labels, values, color=colors, height=0.62)
    ax.set_xlim(0, 1.15)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Missing", "Found"])
    ax.set_title("Section detection", color=TEXT, fontsize=11, loc="left", pad=10)
    for index, value in enumerate(values):
        ax.text(
            0.03 if value == 0 else 0.85,
            index,
            "not found" if value == 0 else "detected",
            va="center",
            fontsize=8,
            color=MUTED if value == 0 else "#ffffff",
        )
    return _save(fig, "sections")


def score_radar_chart(score_report) -> Optional[str]:
    """Balance of the four scoring components plus the overall score."""
    if score_report is None:
        return None

    labels = ["Structure", "Content", "Skills", "ATS", "Overall"]
    values = [component.score for component in score_report.components]
    values.append(score_report.overall)
    return _radar(labels, values, "Score balance across components", "radar")


def ats_checks_radar_chart(ats_report) -> Optional[str]:
    """The eight ATS readability checks as one radar shape."""
    if ats_report is None:
        return None

    checks = list(getattr(ats_report, "checks", []) or [])
    if len(checks) < 3:
        return None

    labels, values = [], []
    for check in checks:
        max_score = float(getattr(check, "max_score", 0) or 0)
        if max_score <= 0:
            continue
        labels.append(check.label)
        values.append(max(0.0, min(100.0, check.score / max_score * 100.0)))

    return _radar(labels, values, "ATS readability checks", "ats_radar")


# Imported lazily to avoid a circular import at module load.
SECTION_ORDER_LABELS = []

def _init_section_labels() -> None:
    from backend.resume_parser import (
        OPTIONAL_SECTIONS,
        RECOMMENDED_SECTIONS,
        SECTION_LABELS,
    )

    global SECTION_ORDER_LABELS
    SECTION_ORDER_LABELS = [
        (key, SECTION_LABELS[key])
        for key in RECOMMENDED_SECTIONS + OPTIONAL_SECTIONS
    ]


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------
def generate_all_charts(resume, profile, score_report, job_result=None, ats_report=None) -> Dict:
    """
    Build every chart the dashboard needs.

    Returns a mapping ``{chart_key: url}``. A failing chart is simply left out
    of the mapping - analysis results are never blocked by a plotting problem.
    """
    _init_section_labels()

    charts: Dict[str, str] = {}
    builders = [
        ("scores", lambda: score_distribution_chart(score_report)),
        ("radar", lambda: score_radar_chart(score_report)),
        ("ats_radar", lambda: ats_checks_radar_chart(ats_report)),
        ("skills", lambda: skill_category_chart(profile)),
        ("keywords", lambda: keyword_frequency_chart(profile)),
        ("sections", lambda: section_coverage_chart(resume)),
        ("job_match", lambda: job_match_chart(job_result)),
    ]

    for key, builder in builders:
        try:
            url = builder()
            if url:
                charts[key] = url
        except Exception:  # noqa: BLE001
            continue

    # Prune here rather than on page load: every generation path (web form,
    # JSON API, smoke test) now keeps the folder bounded.
    cleanup_old_charts()
    return charts


def add_role_fit_chart(result: Dict) -> None:
    """Second pass: add the all-roles chart once role ranking is available."""
    try:
        url = role_fit_chart(result.get("role_overview") or [])
        if url:
            result.setdefault("charts", {})["role_fit"] = url
    except Exception:  # noqa: BLE001
        pass
    else:
        cleanup_old_charts()


def cleanup_old_charts(max_files: int = 40) -> None:
    """Delete old generated PNGs so the repo folder does not grow forever."""
    if INLINE_CHARTS:
        return  # nothing is ever written to disk in inline mode
    try:
        if not os.path.isdir(STATIC_CHART_DIR):
            return
        files = [
            os.path.join(STATIC_CHART_DIR, name)
            for name in os.listdir(STATIC_CHART_DIR)
            if name.endswith(".png")
        ]
        files.sort(key=os.path.getmtime, reverse=True)
        for stale in files[max_files:]:
            try:
                os.remove(stale)
            except OSError:
                pass
    except Exception:  # noqa: BLE001
        pass