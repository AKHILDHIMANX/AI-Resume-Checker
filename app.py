"""
AI Resume Checker - AI-Based Resume Analyzer
===================================

Flask entry point for the project.

Routes
------
``GET  /``                 Landing page
``GET  /analyze``          Upload + job role selection form
``POST /analyze``          Validate, parse, analyse, render the dashboard
``GET  /report/download``  Download the plain-text analysis report
``POST /api/analyze``      Same analysis as JSON (used by the progress UI)
``GET  /api/roles``        JSON list of supported job roles
``GET  /methodology``      How every score is calculated
``GET  /about``            Project information

Privacy
-------
Uploaded PDFs are written to ``uploads/`` with a random safe filename, are
never served statically and are deleted as soon as the analysis finishes (see
``DELETE_UPLOAD_AFTER_ANALYSIS``, on by default).

MCA Semester 1 project - Python Programming.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.utils import secure_filename

from backend import charts as chart_module
from backend import job_matcher
from backend.analyzer import AnalysisError, analyze_resume, build_plain_text_report
from backend.resume_parser import EmptyPDFError, InvalidPDFError, ResumeParseError
from backend.skill_data import SkillDataError
from backend.job_matcher import JobDataError, UnknownRoleError

# --------------------------------------------------------------------------
# Application setup
# --------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

ALLOWED_EXTENSIONS = {".pdf"}


def _env_float(name: str, default: float) -> float:
    """Read a positive float from the environment, ignoring bad values."""
    try:
        value = float(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _writable_dir() -> str:
    """
    Return a directory this process can actually write to.

    A normal machine (and the Vercel build step) can write inside the project,
    so that is tried first and the layout stays as documented. A serverless
    runtime mounts the project read-only and permits writes only under the
    system temporary directory, so that is used instead. The location is probed
    rather than assumed, because guessing wrong fails at the first upload.
    """
    preferred = os.environ.get("STORAGE_DIR") or BASE_DIR
    fallback = os.path.join(tempfile.gettempdir(), "ai-resume-checker")
    for candidate in (preferred, fallback):
        try:
            os.makedirs(candidate, exist_ok=True)
            probe = os.path.join(candidate, ".write-probe")
            with open(probe, "w", encoding="utf-8") as handle:
                handle.write("ok")
            os.remove(probe)
            return candidate
        except OSError:
            continue
    # Nothing is writable. Analysis still works because nothing below treats
    # storage as mandatory; each write site handles its own failure.
    return tempfile.gettempdir()


STORAGE_DIR = _writable_dir()
UPLOAD_DIR = os.path.join(STORAGE_DIR, "uploads")
REPORTS_DIR = os.path.join(STORAGE_DIR, "reports")

# Vercel rejects a request body above 4.5 MB, so the default upload limit is
# kept below that. Raise MAX_FILE_MB on a host with no such limit.
MAX_FILE_SIZE_MB = int(_env_float("MAX_FILE_MB", 4))
MAX_CONTENT_LENGTH = MAX_FILE_SIZE_MB * 1024 * 1024

# Static assets live under public/static rather than a top-level static/
# folder. Vercel serves everything in public/ from its CDN at the matching
# URL, so /static/css/style.css is delivered without starting the application.
# Pointing Flask at the same directory keeps local development identical and
# leaves one copy of each file rather than two.
app = Flask(__name__, static_folder="public/static", static_url_path="/static")
app.config.update(
    MAX_CONTENT_LENGTH=MAX_CONTENT_LENGTH,
    UPLOAD_FOLDER=UPLOAD_DIR,
    # Secret key is read from the environment so nothing sensitive lives in
    # source control. A random key is generated for local development only.
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    JSON_SORT_KEYS=False,
    DELETE_UPLOAD_AFTER_ANALYSIS=os.environ.get("KEEP_UPLOADS", "0") != "1",
)

# Every PDF starts with this marker. A file that claims to be a PDF but does
# not start with it is rejected before any parser sees it. Real PDFs may carry
# leading whitespace, so a short prefix search is used rather than startswith.
PDF_MAGIC = b"%PDF-"


def looks_like_pdf(data: bytes) -> bool:
    """True when the first bytes of a file are the PDF file signature."""
    return PDF_MAGIC in data[:1024]


# Both directories are normally created by _writable_dir(). These calls cover
# the case where the process cannot write anywhere: failing to start would be a
# worse outcome than starting with no storage, and every write site below
# already handles its own failure.
for _directory in (UPLOAD_DIR, REPORTS_DIR):
    try:
        os.makedirs(_directory, exist_ok=True)
    except OSError:  # pragma: no cover - only on a fully read-only filesystem
        pass


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def allowed_file(filename: str) -> bool:
    """Only accept a file whose extension is ``.pdf``."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() == "pdf"


def safe_upload_name(original_name: str) -> str:
    """
    Build a collision-proof, filesystem-safe name for an upload.

    The user filename is sanitised with ``secure_filename`` (so no path
    traversal or shell metacharacters survive) and a random token is appended,
    meaning two users uploading ``resume.pdf`` never overwrite each other and
    the original name is not exposed on disk.
    """
    cleaned = secure_filename(original_name or "resume.pdf")
    cleaned = cleaned or "resume.pdf"
    # Keep the extension check aligned with allowed_file().
    stem, ext = os.path.splitext(cleaned)
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", stem)[:40] or "resume"
    return f"{stem}_{uuid.uuid4().hex[:10]}{ext.lower()}"


def format_file_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"


def human_error(exc: Exception) -> str:
    """Map an exception to a message that is safe and useful for the user."""
    if isinstance(exc, InvalidPDFError):
        return str(exc)
    if isinstance(exc, EmptyPDFError):
        return str(exc)
    if isinstance(exc, UnknownRoleError):
        return str(exc)
    if isinstance(exc, (JobDataError, SkillDataError)):
        return "Project data files could not be loaded. Please check data/skills.json."
    if isinstance(exc, AnalysisError):
        return f"The analysis could not be completed: {exc}"
    if isinstance(exc, ResumeParseError):
        return str(exc)
    return "Something unexpected went wrong while analysing the resume. Please try again."


def get_role_options() -> list:
    """Job roles for the dropdown; degrades gracefully if the data file fails."""
    try:
        return job_matcher.list_roles()
    except JobDataError:
        return []


# --------------------------------------------------------------------------
# Routes: pages
# --------------------------------------------------------------------------
@app.route("/")
def index():
    """Landing page."""
    return render_template(
        "index.html",
        roles=get_role_options(),
        max_size_mb=MAX_FILE_SIZE_MB,
        stats=_project_stats(),
    )


@app.route("/analyze", methods=["GET", "POST"])
def analyze():
    """
    Upload form (GET) and analysis (POST).

    On success the full report is written to ``reports/<id>.json`` and the
    dashboard is rendered. The uploaded PDF is deleted immediately after the
    analysis unless ``KEEP_UPLOADS=1`` is set in the environment.
    """
    if request.method == "GET":
        return render_template(
            "upload.html",
            roles=get_role_options(),
            max_size_mb=MAX_FILE_SIZE_MB,
        )

    uploaded = request.files.get("resume")
    job_role = (request.form.get("job_role") or "").strip()

    # 1. Was a file submitted at all?
    if uploaded is None or not uploaded.filename:
        flash("Please choose a PDF resume before starting the analysis.", "error")
        return redirect(url_for("analyze"))

    original_name = uploaded.filename

    # 2. Extension check
    if not allowed_file(original_name):
        flash(
            f"'{original_name}' is not supported. AI Resume Checker accepts PDF files only.",
            "error",
        )
        return redirect(url_for("analyze"))

    stored_name = safe_upload_name(original_name)
    stored_path = os.path.join(UPLOAD_DIR, stored_name)

    try:
        # 3. Read and size-check the upload
        file_bytes = uploaded.read()
        if not file_bytes:
            flash("The selected file is empty (0 bytes). Please upload a valid PDF.", "error")
            return redirect(url_for("analyze"))

        size_mb = len(file_bytes) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            flash(
                f"The file is {size_mb:.1f} MB. The upload limit is "
                f"{MAX_FILE_SIZE_MB} MB. Please compress or reduce the file size.",
                "error",
            )
            return redirect(url_for("analyze"))

        # 4. Content check: a renamed .txt or .png must not reach the parser.
        if not looks_like_pdf(file_bytes):
            flash(
                f"'{original_name}' does not look like a real PDF file. "
                "Please export your resume as a text-based PDF.",
                "error",
            )
            return redirect(url_for("analyze"))

        # 5. Save under the safe random name (never served statically)
        with open(stored_path, "wb") as handle:
            handle.write(file_bytes)

        # 6. Analyse
        started = time.perf_counter()
        result = analyze_resume(
            file_bytes=file_bytes,
            job_role=job_role or None,
            filename=original_name,
        )
        elapsed = time.perf_counter() - started
        result.setdefault("meta", {})["elapsed_seconds"] = round(elapsed, 2)

        report_id = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
        _save_report(result, report_id)

    except UnknownRoleError as exc:
        flash(str(exc), "error")
        return redirect(url_for("analyze"))
    except ResumeParseError as exc:
        flash(str(exc), "error")
        return redirect(url_for("analyze"))
    except AnalysisError as exc:
        flash(human_error(exc), "error")
        return redirect(url_for("analyze"))
    except Exception as exc:  # noqa: BLE001 - last resort, never show a traceback
        app.logger.exception("Unexpected failure while analysing an upload")
        flash(human_error(exc), "error")
        return redirect(url_for("analyze"))
    finally:
        # 7. Privacy: remove the uploaded PDF as soon as it is not needed.
        if app.config["DELETE_UPLOAD_AFTER_ANALYSIS"]:
            try:
                if os.path.exists(stored_path):
                    os.remove(stored_path)
            except OSError:  # pragma: no cover
                pass

    if result.get("job_match_error"):
        flash(result["job_match_error"], "warn")

    flash(
        f"Analysis complete in {elapsed:.2f} seconds - "
        f"{format_file_size(len(file_bytes))} analysed.",
        "success",
    )

    # Redirect after POST so the dashboard has a real URL: it can be reloaded,
    # bookmarked and shared, and a browser refresh never re-uploads the PDF.
    # This also lets the flash messages set above appear on the next render.
    return redirect(url_for("results", report_id=report_id))


def _render_results(result: dict, report_id: str, elapsed: float):
    """Render the dashboard from a stored analysis result."""
    return render_template(
        "results.html",
        result=result,
        report_id=report_id,
        elapsed=elapsed,
        scores=result["scores"],
        overview=result["overview"],
        skills=result["skills"],
        ats=result["ats"],
        job=result["job_match"],
        advice=result["advice"],
        charts=result["charts"],
        roles=get_role_options(),
    )


@app.route("/results/<report_id>")
def results(report_id: str):
    """Re-open a stored analysis dashboard by its report id."""
    safe_id = secure_filename(report_id or "")
    if not safe_id:
        flash("Invalid report reference.", "error")
        return redirect(url_for("index"))

    result, _text, status = _recall_report(safe_id)
    if status == "unreadable":
        flash("That analysis could not be read. Please run it again.", "warn")
        return redirect(url_for("analyze"))
    if result is None:
        flash(
            "That analysis is no longer available. Please upload your resume again.",
            "warn",
        )
        return redirect(url_for("analyze"))

    elapsed = float(result.get("meta", {}).get("elapsed_seconds") or 0.0)
    return _render_results(result, safe_id, elapsed)


@app.route("/report/<report_id>")
def download_report(report_id: str):
    """Download the generated plain-text analysis report."""
    safe_id = secure_filename(report_id or "")
    if not safe_id:
        flash("Invalid report reference.", "error")
        return redirect(url_for("index"))

    _result, text, status = _recall_report(safe_id)
    if status == "unreadable":
        flash("That report could not be read. Please run the analysis again.", "warn")
        return redirect(url_for("index"))
    if not text:
        flash("That report is no longer available. Please run the analysis again.", "warn")
        return redirect(url_for("index"))

    return Response(
        text,
        mimetype="text/plain",
        headers={"Content-Disposition": f'attachment; filename="AI_Resume_Checker_Report_{safe_id}.txt"'},
    )


@app.route("/api/report/<report_id>")
def report_json(report_id: str):
    """Return the stored analysis JSON (same store as the text report)."""
    safe_id = secure_filename(report_id or "")
    result, _text, _status = _recall_report(safe_id)
    if result is None:
        return jsonify({"error": "Report not found."}), 404
    return jsonify(result)


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """
    JSON analysis endpoint.

    Accepts ``multipart/form-data`` with a ``resume`` file and an optional
    ``job_role`` field. Used by the progress bar in ``static/js/script.js``.
    """
    uploaded = request.files.get("resume")
    job_role = (request.form.get("job_role") or "").strip()

    if uploaded is None or not uploaded.filename:
        return jsonify({"ok": False, "error": "No file was uploaded."}), 400
    if not allowed_file(uploaded.filename):
        return jsonify(
            {
                "ok": False,
                "error": f"'{uploaded.filename}' is not a PDF. Only PDF files are accepted.",
            }
        ), 400

    file_bytes = uploaded.read()
    if not file_bytes:
        return jsonify({"ok": False, "error": "The uploaded file is empty."}), 400
    if len(file_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        return jsonify(
            {"ok": False, "error": f"File is larger than {MAX_FILE_SIZE_MB} MB."}
        ), 400
    if not looks_like_pdf(file_bytes):
        return jsonify(
            {
                "ok": False,
                "error": "The uploaded file does not contain PDF data.",
            }
        ), 400

    try:
        result = analyze_resume(file_bytes, job_role or None, uploaded.filename)
    except UnknownRoleError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except ResumeParseError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("API analysis failure")
        return jsonify({"ok": False, "error": human_error(exc)}), 500

    return jsonify({"ok": True, "result": result})


@app.route("/api/roles")
def api_roles():
    """List of supported job roles (used to populate the dropdown)."""
    try:
        return jsonify({"ok": True, "roles": job_matcher.list_roles()})
    except JobDataError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/methodology")
def methodology():
    """Transparent explanation of how each score is computed."""
    from backend import scoring

    checks = [
        {
            "label": "Standard section headings",
            "points": "0-22",
            "rule": "Detected standard headings / 5 recommended sections x 22",
        },
        {
            "label": "Contact information",
            "points": "0-16",
            "rule": "email 7.2 + phone 5.6 + name 3.2",
        },
        {
            "label": "Text readability",
            "points": "0-16",
            "rule": "60% extracted text volume + 40% special-character penalty",
        },
        {
            "label": "Resume length",
            "points": "0-12",
            "rule": "250-850 words (65%) + 1-2 pages (35%)",
        },
        {
            "label": "Excessive special formatting",
            "points": "0-8",
            "rule": "Penalty scaled by special characters per 1000 characters",
        },
        {
            "label": "Bullet point structure",
            "points": "0-8",
            "rule": "Bullets found / 10, reduced for very long lines",
        },
        {
            "label": "Keyword presence",
            "points": "0-10",
            "rule": "70% skill coverage + 30% role keyword hits",
        },
        {
            "label": "Section completeness",
            "points": "0-8",
            "rule": "Core sections full weight, optional sections half weight",
        },
    ]

    return render_template(
        "methodology.html",
        overall_weights=scoring.OVERALL_WEIGHTS,
        structure_weights=scoring.STRUCTURE_WEIGHTS,
        content_weights=scoring.CONTENT_WEIGHTS,
        skills_weights=scoring.SKILLS_WEIGHTS,
        ats_checks=checks,
        job_weights={
            "Core skill": "3",
            "Preferred skill": "2",
            "Bonus skill": "1",
            "Final blend": "0.65 x skill coverage + 0.35 x TF-IDF cosine similarity",
        },
    )


@app.route("/about")
def about():
    """Project overview / academic context page."""
    return render_template("about.html", stats=_project_stats())


@app.route("/health")
def health():
    """Tiny health check used by the developer to confirm the server is up."""
    return jsonify(
        {
            "status": "ok",
            "app": "AI Resume Checker",
            "roles_loaded": len(get_role_options()),
        }
    )


# --------------------------------------------------------------------------
# Error handlers - friendly pages, never a raw traceback
# --------------------------------------------------------------------------
@app.errorhandler(413)
def too_large(_error):
    flash(
        f"The uploaded file is larger than {MAX_FILE_SIZE_MB} MB. "
        "Please upload a smaller, text-based PDF.",
        "error",
    )
    return redirect(url_for("analyze"))


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404,
                           title="Page not found",
                           message="The page you requested does not exist."), 404


@app.errorhandler(500)
def server_error(_error):  # pragma: no cover
    app.logger.exception("Unhandled server error")
    return render_template(
        "error.html",
        code=500,
        title="Something went wrong",
        message="An unexpected error occurred. Please go back and try again.",
    ), 500


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------
# How many analyses to keep in memory. Bounds growth on a long-running server
# while comfortably covering a session of normal use.
MEMORY_REPORTS = 20

_REPORT_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_REPORT_CACHE_LOCK = threading.Lock()


def _remember_report(report_id: str, result: dict, text: str) -> None:
    """Keep the newest analyses in memory so they survive a read-only disk."""
    with _REPORT_CACHE_LOCK:
        _REPORT_CACHE[report_id] = {"result": result, "text": text}
        while len(_REPORT_CACHE) > MEMORY_REPORTS:
            _REPORT_CACHE.popitem(last=False)


def _cached(report_id: str):
    """Return the in-memory copy of an analysis as ``(result, text)``.

    Both fields are ``None`` when nothing is held for this id.
    """
    with _REPORT_CACHE_LOCK:
        entry = _REPORT_CACHE.get(report_id)
    if entry is None:
        return None, None
    return entry["result"], entry["text"]


def _recall_report(report_id: str):
    """Return ``(result, text, status)`` for a stored analysis.

    ``status`` is ``"ok"``, ``"missing"`` (nothing stored under this id) or
    ``"unreadable"`` (a file exists but could not be parsed). The callers turn
    those into different messages, so the distinction is kept here.

    The file on disk is consulted first because it is the only copy that
    outlives the process. The in-memory copy is a fallback for a host with a
    read-only filesystem, where nothing was written in the first place. A file
    that exists but is corrupt is reported rather than silently replaced by the
    cached copy, because a corrupt file means the stored data is unreliable and
    the user is better served by being told to run the analysis again.
    """
    json_path = os.path.join(REPORTS_DIR, f"{report_id}.json")

    try:
        with open(json_path, encoding="utf-8") as handle:
            result = json.load(handle)
    except ValueError as exc:
        # The file is there but does not hold valid JSON, which is what a
        # partial write leaves behind.
        app.logger.warning("Could not read stored report %s: %s", report_id, exc)
        return None, None, "unreadable"
    except OSError as exc:
        if os.path.exists(json_path):
            app.logger.warning("Could not read stored report %s: %s", report_id, exc)
            return None, None, "unreadable"
        # Nothing readable at that path, which covers both a report that was
        # never stored and a filesystem that refused the write. Either way the
        # in-memory copy is the only one that can exist.
        result, text = _cached(report_id)
        if result is None:
            return None, None, "missing"
        return result, text, "ok"

    try:
        with open(os.path.join(REPORTS_DIR, f"{report_id}.txt"), encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        # The dashboard still works without the downloadable text version.
        text = ""

    return result, text, "ok"


def _save_report(result: dict, report_id: str) -> None:
    """Persist the analysis as JSON + plain text, and remember it in memory."""
    try:
        text = build_plain_text_report(result)
    except Exception:  # noqa: BLE001 - a text report must never block the result
        app.logger.warning("Could not build text report %s", report_id)
        text = ""

    _remember_report(report_id, result, text)

    try:
        with open(os.path.join(REPORTS_DIR, f"{report_id}.json"), "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
    except OSError:  # pragma: no cover - expected on a read-only filesystem
        app.logger.info("Reports directory is not writable; using memory only")

    if text:
        try:
            with open(os.path.join(REPORTS_DIR, f"{report_id}.txt"), "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError:  # pragma: no cover
            app.logger.info("Reports directory is not writable; using memory only")


def _project_stats() -> dict:
    """Real counts for the landing page - no invented numbers."""
    from backend.skill_data import load_skill_data, soft_skills, technical_skills

    stats = {
        "job_roles": 0,
        "skills": 0,
        "categories": 0,
        "soft_skills": 0,
    }
    try:
        stats["job_roles"] = len(job_matcher.load_job_roles())
    except JobDataError:
        pass
    try:
        categories = technical_skills()
        stats["categories"] = len(categories)
        stats["skills"] = len({s for skills in categories.values() for s in skills})
        stats["soft_skills"] = len(soft_skills())
    except SkillDataError:
        pass
    return stats


# --------------------------------------------------------------------------
# Local development server
# --------------------------------------------------------------------------
if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    print("=" * 58)
    print("  AI Resume Checker - AI-Based Resume Analyzer")
    print("  MCA Semester 1 project")
    print("=" * 58)
    print(f"  Running on  : http://{host}:{port}")
    print(f"  Upload limit: {MAX_FILE_SIZE_MB} MB (PDF only)")
    print("  Stop server : press Ctrl+C")
    print("=" * 58)

    app.run(host=host, port=port, debug=debug)