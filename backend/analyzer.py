"""
Analyzer orchestrator.

Ties the individual modules together:

    PDF bytes
      -> resume_parser.parse_resume()      (extract, clean, sections, fields)
      -> skill_extractor.extract_skills()  (technical / soft / keywords)
      -> job_matcher.match_job()           (optional target role)
      -> ats_analyzer.analyze_ats()        (ATS estimate)
      -> scoring.calculate_scores()        (weighted scores)
      -> charts                            (matplotlib PNGs)
      -> advice                            (strengths / weaknesses / suggestions)

Optional external AI
--------------------
If ``OPENAI_API_KEY`` (or ``GEMINI_API_KEY``) is present in the environment and
``ENABLE_AI_ASSIST`` is not "0", an *optional* external model is asked to
rewrite the improvement suggestions in better English. The application never
depends on it: without a key (or without network access) the local rule based
suggestions are used unchanged. No fake responses are ever produced.
"""

from __future__ import annotations

import os
import re
import textwrap
from datetime import datetime
from typing import Dict, List, Optional

from backend import ats_analyzer, job_matcher, scoring
from backend.resume_parser import (
    ParsedResume,
    ResumeParseError,
    SECTION_LABELS,
    parse_resume,
)
from backend.skill_extractor import SkillProfile, extract_skills


class AnalysisError(Exception):
    """Raised when analysis fails unexpectedly."""


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def analyze_resume(
    file_bytes: bytes,
    job_role: Optional[str] = None,
    filename: str = "resume.pdf",
) -> Dict:
    """
    Run the complete analysis pipeline and return a JSON-ready report.

    Args:
        file_bytes: raw bytes of the uploaded PDF
        job_role: optional target role (name or alias)
        filename: original filename, used only for the report header

    Raises:
        ResumeParseError: invalid / unusable PDF
        job_matcher.UnknownRoleError: role not in the dataset
        AnalysisError: any other unexpected failure
    """
    try:
        resume = parse_resume(file_bytes)
    except ResumeParseError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AnalysisError(f"Resume parsing failed: {exc}") from exc

    profile = extract_skills(resume.clean_text, resume.section_text)

    # --- job matching (optional) ----------------------------------------
    role_keywords: List[str] = []
    job_result = None
    job_error = None
    if job_role and job_role.strip():
        try:
            job_result = job_matcher.match_job(
                resume.clean_text, job_role, resume_skills=profile.technical
            )
            role_keywords = job_result.matched_keywords + job_result.missing_keywords
        except job_matcher.UnknownRoleError as exc:
            job_error = str(exc)
        except job_matcher.JobDataError as exc:  # pragma: no cover
            job_error = str(exc)

    # --- ATS estimate ----------------------------------------------------
    ats_report = ats_analyzer.analyze_ats(resume, profile.technical, role_keywords)

    # --- scores ----------------------------------------------------------
    job_score = job_result.match_score if job_result else None
    score_report = scoring.calculate_scores(resume, profile, ats_report.score, job_score)

    # --- advice ----------------------------------------------------------
    advice = build_advice(resume, profile, ats_report, score_report, job_result)
    advice = _maybe_enhance_with_ai(advice)

    # --- charts ----------------------------------------------------------
    charts = {}
    try:
        from backend import charts as chart_module

        charts = chart_module.generate_all_charts(
            resume, profile, score_report, job_result, ats_report
        )
    except Exception as exc:  # noqa: BLE001 - charts are optional decoration
        charts = {"error": str(exc)}

    # --- role overview ---------------------------------------------------
    # Rank every role in the dataset, not just the selected one. The set is
    # small (10 roles) and truncating it would hide honest comparisons.
    role_overview = []
    try:
        role_overview = job_matcher.rank_roles(resume.clean_text, top_n=None)
    except Exception:  # noqa: BLE001
        role_overview = []

    parsed = resume.to_dict()

    report = {
        "meta": {
            "filename": filename,
            "analyzed_at": datetime.now().strftime("%d %b %Y, %I:%M %p"),
            "file_size_kb": round(len(file_bytes) / 1024, 1),
            "pipeline": [
                "PDF text extraction (pypdf + pdfplumber)",
                "Text cleaning and normalisation",
                "Section heading detection",
                "Field extraction (regex)",
                "Skill matching (regex + alias map)",
                "TF-IDF keyword extraction",
                "Cosine similarity job matching",
                "ATS readability estimate",
                "Weighted score aggregation",
            ],
        },
        "overview": {
            "name": resume.contact.name or "Name not detected",
            "pages": resume.pages,
            "word_count": resume.word_count,
            "char_count": resume.char_count,
            "sections_found": resume.sections_found,
            "sections_found_labels": [SECTION_LABELS[key] for key in resume.sections_found],
            "sections_missing": resume.sections_missing,
            "contact": parsed["contact"],
            "contact_completeness": parsed["contact_completeness"],
            "metrics": resume.metrics,
        },
        "skills": profile.to_dict(),
        "education": parsed["education"],
        "experience": parsed["experience"],
        "projects": parsed["projects"],
        "certifications": parsed["certifications"],
        "achievements": parsed["achievements"],
        "languages": parsed["languages"],
        "interests": parsed["interests"],
        "summary_text": parsed["summary_text"],
        "scores": score_report.to_dict(),
        "ats": ats_report.to_dict(),
        "job_match": job_result.to_dict() if job_result else None,
        "job_match_error": job_error,
        "role_overview": role_overview,
        "missing_sections": scoring.missing_section_labels(resume),
        "optional_sections": scoring.optional_section_labels(resume),
        "advice": advice,
        "charts": charts,
    }

    # The all-roles chart needs the ranking, so it is added in a second pass.
    try:
        from backend import charts as chart_module

        chart_module.add_role_fit_chart(report)
    except Exception:  # noqa: BLE001
        pass

    return report


# --------------------------------------------------------------------------
# Advice generation (rule based, fully explainable)
# --------------------------------------------------------------------------
def build_advice(
    resume: ParsedResume,
    profile: SkillProfile,
    ats_report: ats_analyzer.ATSReport,
    score_report: scoring.ScoreReport,
    job_result: Optional[job_matcher.JobMatchResult],
) -> Dict:
    """Turn analysis output into strengths, weaknesses and recommendations."""
    strengths: List[Dict] = []
    weaknesses: List[Dict] = []
    recommendations: List[Dict] = []

    def add(bucket: List[Dict], title: str, detail: str, priority: str = "Medium") -> None:
        bucket.append({"title": title, "detail": detail, "priority": priority})

    # ---------------- Strengths ----------------------------------------
    if resume.contact.completeness == 100:
        add(
            strengths,
            "Complete contact block",
            "Name, email and phone number were all detected, which is the "
            "minimum an automated parser needs.",
        )
    if "summary" in resume.sections_found and len(resume.summary_text.split()) >= 25:
        add(
            strengths,
            "Well sized profile / summary",
            f"A {len(resume.summary_text.split())} word summary tells the reader "
            "your direction immediately.",
        )
    if len(profile.technical) >= 10:
        add(
            strengths,
            "Good technical skill breadth",
            f"{len(profile.technical)} named technologies were detected "
            f"across {len(profile.technical_by_category)} categories.",
        )
    if profile.quantifier_count >= TARGET_QUANTIFIER_HINT:
        add(
            strengths,
            "Quantified achievements",
            f"{profile.quantifier_count} measurable results (percentages, volumes "
            "or currency) were found - this is exactly what recruiters scan for.",
        )
    if len(profile.action_verbs) >= 5:
        add(
            strengths,
            "Action-oriented wording",
            f"{len(profile.action_verbs)} different action verbs (developed, "
            "designed, implemented...) were used.",
        )
    if resume.experience:
        add(
            strengths,
            "Experience section present",
            f"{len(resume.experience)} experience/internship entries were parsed.",
        )
    elif resume.projects:
        add(
            strengths,
            "Project section present",
            f"{len(resume.projects)} project entries were parsed - strong "
            "evidence of practical ability for a fresher.",
        )
    if resume.education:
        add(
            strengths,
            "Education details parsed",
            f"{len(resume.education)} education entries with degree/institution/year.",
        )
    for check in ats_report.checks:
        if check.key == "standard_headings" and check.status == "good":
            add(
                strengths,
                "Standard section headings",
                "Conventional headings such as Education, Skills and Experience "
                "make automated parsing reliable.",
            )
        if check.key == "readable_text" and check.status == "good":
            add(
                strengths,
                "Clean text layer",
                "The PDF contains selectable text, so the file is not a scan.",
            )

    if not strengths:
        add(
            strengths,
            "Resume was analysed successfully",
            "The file is a valid, text-based PDF - start by adding clearly "
            "labelled sections to build on this.",
            "Low",
        )

    # ---------------- Weaknesses ---------------------------------------
    for item in scoring.missing_section_labels(resume):
        add(
            weaknesses,
            f"Missing section: {item['label']}",
            item["reason"],
            "High" if item["key"] in {"skills", "education", "experience"} else "Medium",
        )

    if not resume.contact.emails:
        add(
            weaknesses,
            "No email address detected",
            "Add a plain-text email address (for example name@gmail.com) in the "
            "header. Many filters reject resumes without one.",
            "High",
        )
    if not resume.contact.phones:
        add(
            weaknesses,
            "No phone number detected",
            "Add a contact number in a standard format such as +91 98765 43210.",
            "High",
        )
    if resume.word_count < 250:
        add(
            weaknesses,
            "Very little content",
            f"Only {resume.word_count} words could be read. A fresher resume "
            "usually needs at least 250 words to communicate skills properly.",
            "High",
        )
    elif resume.word_count > 850:
        add(
            weaknesses,
            "Resume is quite long",
            f"{resume.word_count} words is longer than the recommended 250-850. "
            "Remove content that is not relevant to the target role.",
            "Medium",
        )
    if profile.quantifier_count < 2:
        add(
            weaknesses,
            "No measurable results",
            "Bullets describe duties but not outcomes. Add numbers - for example "
            "'reduced report generation time by 30%'.",
            "High",
        )
    if len(profile.action_verbs) < 3:
        add(
            weaknesses,
            "Few action verbs",
            "Start bullet points with strong verbs such as developed, designed, "
            "implemented, automated or improved.",
            "Medium",
        )
    if profile.filler_count > 2:
        add(
            weaknesses,
            "Vague phrases detected",
            f"{profile.filler_count} occurrences of phrases such as 'responsible "
            "for' or 'etc.'. Replace them with the actual result you produced.",
            "Medium",
        )
    if len(profile.technical) < 6:
        add(
            weaknesses,
            "Few named technologies",
            f"Only {len(profile.technical)} skills from the internal vocabulary "
            "were found. Name the exact tools you used.",
            "High",
        )
    if len(profile.soft) < 2:
        add(
            weaknesses,
            "Soft skills not demonstrated",
            "Add 3-5 soft skills (communication, teamwork, problem solving) with "
            "a short example of where you used them.",
            "Medium",
        )
    if resume.metrics.get("special_char_ratio", 0) > 10:
        add(
            weaknesses,
            "Heavy special formatting",
            "Decorative symbols and emoji confuse keyword extraction. Stick to "
            "plain text and simple bullets.",
            "Medium",
        )
    if resume.metrics.get("bullet_count", 0) < 4:
        add(
            weaknesses,
            "Few bullet points",
            "The resume reads as paragraphs. Break responsibilities into short "
            "bullet points starting with an action verb.",
            "Medium",
        )
    if resume.pages > 2:
        add(
            weaknesses,
            f"{resume.pages} pages",
            "Keep the resume to 1-2 pages for a student or fresher profile.",
            "Medium",
        )

    # ---------------- Recommendations ----------------------------------
    seen_titles = set()

    def recommend(title: str, detail: str, priority: str) -> None:
        if title in seen_titles:
            return
        seen_titles.add(title)
        add(recommendations, title, detail, priority)

    for item in scoring.missing_section_labels(resume):
        recommend(
            f"Add a '{item['label']}' section",
            item["reason"],
            "High" if item["key"] in {"skills", "experience", "education"} else "Medium",
        )

    for suggestion in ats_report.suggestions[:5]:
        recommend("ATS formatting fix", suggestion, "Medium")

    if profile.quantifier_count < TARGET_QUANTIFIER_HINT:
        recommend(
            "Quantify at least 4 achievements",
            "Rewrite bullets as 'Action + Result + Metric', for example "
            "'Processed 5,000 records per run using Pandas, cutting manual "
            "effort by 40%'.",
            "High",
        )
    if len(profile.technical) < TARGET_SKILLS_BREADTH:
        recommend(
            "Expand the skills section",
            "Group skills into Technical Skills and Tools, and list 12-18 "
            "technologies you have actually used.",
            "High",
        )
    if len(profile.soft) < 3:
        recommend(
            "Add soft skills with evidence",
            "Add communication, teamwork, problem solving and time management - "
            "each with a one-line example.",
            "Medium",
        )

    if job_result:
        missing_core = job_result.missing_core
        if missing_core:
            recommend(
                f"Add these core skills for '{job_result.role}'",
                "The role profile lists " + ", ".join(missing_core[:6])
                + " and the resume does not mention them yet.",
                "High",
            )
        missing_kw = job_result.missing_keywords
        if missing_kw:
            recommend(
                "Mirror the job description vocabulary",
                "These role keywords were not found in the resume: "
                + ", ".join(missing_kw[:8]) + ".",
                "Medium",
            )
        recommend(
            "Tailor the summary to the target role",
            f"Rewrite the 2-3 line summary to mention '{job_result.role}' and the "
            f"skills you already match (e.g. "
            f"{', '.join(job_result.matched_skills[:3]) or 'your strongest tools'}).",
            "Medium",
        )
    else:
        recommend(
            "Re-run the analysis against a target role",
            "Choosing a job role produces a role-specific match score, matched "
            "skills and a missing-skill list.",
            "Low",
        )

    recommend(
        "Keep the layout ATS friendly",
        "Single column, no tables, no text boxes, no images of text. Export as "
        "a text-based PDF named 'Name_Resume.pdf'.",
        "Medium",
    )
    recommend(
        "Proof-read spelling and grammar",
        "Automated checks cannot judge writing quality. Read the resume aloud "
        "once before sending.",
        "Low",
    )

    return {
        "strengths": strengths,
        "weaknesses": weaknesses,
        "recommendations": recommendations,
        "methodology": {
            "overall_weights": scoring.OVERALL_WEIGHTS,
            "structure_weights": scoring.STRUCTURE_WEIGHTS,
            "content_weights": scoring.CONTENT_WEIGHTS,
            "skills_weights": scoring.SKILLS_WEIGHTS,
            "note": (
                "Overall Score = "
                + " + ".join(
                    f"{weight:.2f} x {name.title()} Score"
                    for name, weight in scoring.OVERALL_WEIGHTS.items()
                )
                + ". Job Match is reported separately because it depends on the "
                "selected role."
            ),
        },
    }


TARGET_QUANTIFIER_HINT = 3
TARGET_SKILLS_BREADTH = 12


# --------------------------------------------------------------------------
# Optional external AI enhancement
# --------------------------------------------------------------------------
def _maybe_enhance_with_ai(advice: Dict) -> Dict:
    """
    Optionally rewrite recommendation text with an external LLM.

    Completely optional. Controlled by two environment variables:

    * ``ENABLE_AI_ASSIST``  - set to ``0`` to force local-only suggestions
    * ``OPENAI_API_KEY`` / ``GEMINI_API_KEY`` - credentials read from the
      environment, never stored in source code.

    Any failure (missing key, no network, non-200 response, bad JSON) is
    swallowed and the original local advice is returned, so behaviour is
    identical to the offline path.
    """
    if os.environ.get("ENABLE_AI_ASSIST", "1") == "0":
        return advice

    openai_key = os.environ.get("OPENAI_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not openai_key and not gemini_key:
        return advice

    recommendations = [item["title"] for item in advice["recommendations"]]
    prompt = (
        "Rewrite the following resume improvement suggestions as short, "
        "friendly, actionable sentences for a student or fresher. Keep the "
        "same meaning and return one line per suggestion:\n"
        + "\n".join(f"- {title}" for title in recommendations)
    )

    rewritten = _call_llm(prompt, openai_key, gemini_key)
    if not rewritten:
        return advice

    for item, text in zip(advice["recommendations"], rewritten):
        item["detail"] = text
        item["source"] = "external-ai"
    for item in advice["recommendations"]:
        item.setdefault("source", "local-rules")

    advice["ai_assist_used"] = True
    return advice


def _call_llm(prompt: str, openai_key: Optional[str], gemini_key: Optional[str]) -> Optional[List[str]]:
    """Best-effort call to an optional LLM. Returns None on any problem."""
    import json
    import urllib.error
    import urllib.request

    timeout = float(os.environ.get("AI_REQUEST_TIMEOUT", "8"))

    try:
        if openai_key:
            request = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(
                    {
                        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.4,
                        "max_tokens": 500,
                    }
                ).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {openai_key}",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode())
            content = payload["choices"][0]["message"]["content"]
        else:
            model = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
            request = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}",
                data=json.dumps(
                    {"contents": [{"parts": [{"text": prompt}]}]}
                ).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode())
            content = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError):
        return None
    except Exception:  # noqa: BLE001
        return None

    lines = [re.sub(r"^[-*\d.\s]+", "", line).strip() for line in content.splitlines()]
    lines = [line for line in lines if line]
    return lines or None


# --------------------------------------------------------------------------
# Text helpers used by the report writer
# --------------------------------------------------------------------------
def build_plain_text_report(result: Dict, max_width: int = 88) -> str:
    """
    Render the analysis as a plain-text report.

    Used for the downloadable ``reports/*.txt`` export.
    """
    lines: List[str] = []
    rule = "=" * max_width

    def wrap(text: str, indent: str = "") -> None:
        wrapped = textwrap.wrap(
            str(text), width=max_width, initial_indent=indent, subsequent_indent=indent
        )
        lines.extend(wrapped or [indent.rstrip()])

    scores = result["scores"]
    overview = result["overview"]
    skills = result["skills"]
    ats = result["ats"]
    job = result.get("job_match")

    lines.append(rule)
    lines.append("AI Resume Checker - AI-Based Resume Analyzer")
    lines.append("Analysis report (MCA Semester 1 project)")
    lines.append(rule)
    wrap(f"File            : {result['meta']['filename']}")
    wrap(f"Analysed on     : {result['meta']['analyzed_at']}")
    wrap(f"Pages           : {overview['pages']}")
    wrap(f"Words           : {overview['word_count']}")
    wrap(f"Detected name   : {overview['name']}")
    lines.append("")

    lines.append("SCORES")
    lines.append("-" * max_width)
    wrap(f"Overall Resume Score : {scores['overall']}/100 ({scores['grade']})", "  ")
    for component in scores["components"]:
        wrap(f"{component['label']:<21}: {component['score']}/100", "  ")
    if job:
        wrap(f"{'Job Match Score':<21}: {job['match_score']}/100 ({job['role']})", "  ")
    wrap(f"{'ATS Compatibility':<21}: {ats['score']}/100", "  ")
    lines.append("")

    lines.append("SKILLS DETECTED")
    lines.append("-" * max_width)
    for category, items in skills["technical_by_category"].items():
        wrap(f"{category}: {', '.join(items)}", "  ")
    wrap(f"Soft skills: {', '.join(skills['soft']) or 'none detected'}", "  ")
    lines.append("")

    lines.append("SECTIONS FOUND")
    lines.append("-" * max_width)
    wrap(", ".join(overview["sections_found_labels"]) or "None", "  ")
    lines.append("")

    lines.append("MISSING RECOMMENDED SECTIONS")
    lines.append("-" * max_width)
    missing = result["missing_sections"]
    if missing:
        for item in missing:
            wrap(f"{item['label']} - {item['reason']}", "  - ")
    else:
        wrap("None - all recommended sections are present.", "  ")
    lines.append("")

    if job:
        lines.append(f"JOB ROLE MATCH: {job['role'].upper()}")
        lines.append("-" * max_width)
        wrap(f"Match score      : {job['match_score']}/100", "  ")
        wrap(f"Skill coverage   : {job['skill_coverage_score']}/100", "  ")
        wrap(f"TF-IDF similarity: {job['text_similarity_score']}/100", "  ")
        wrap(f"Matched skills   : {', '.join(job['matched_skills']) or 'none'}", "  ")
        wrap(f"Missing skills   : {', '.join(job['missing_skills']) or 'none'}", "  ")
        lines.append("")

    lines.append("ATS ESTIMATE")
    lines.append("-" * max_width)
    for check in ats["checks"]:
        wrap(f"[{check['status'].upper():<7}] {check['label']}: "
             f"{check['score']}/{check['max_score']}", "  ")
        wrap(check["message"], "      ")
    lines.append("")
    wrap(ats["disclaimer"], "  ")
    lines.append("")

    lines.append("KEYWORD ANALYSIS (TF-IDF)")
    lines.append("-" * max_width)
    keywords = skills["keywords"][:12]
    for item in keywords:
        wrap(f"{item['term']:<28} weight={item['score']:<10} count={item['count']}", "  ")
    lines.append("")

    advice = result["advice"]
    for title, key in (
        ("STRENGTHS", "strengths"),
        ("WEAKNESSES", "weaknesses"),
        ("RECOMMENDATIONS", "recommendations"),
    ):
        lines.append(title)
        lines.append("-" * max_width)
        for item in advice[key]:
            wrap(f"{item['title']}", "  - ")
            wrap(item["detail"], "      ")
        lines.append("")

    lines.append(rule)
    lines.append("Generated by AI Resume Checker. Scores are automated estimates for")
    lines.append("self-assessment only and are not a hiring decision.")
    lines.append(rule)

    return "\n".join(lines)