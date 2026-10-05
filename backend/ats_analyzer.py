"""
ATS (Applicant Tracking System) compatibility estimation.

IMPORTANT
---------
This module produces a *heuristic estimate* of how readable a resume looks to
an automated parser. It does **not** reproduce, emulate or claim to reproduce
the screening logic of any specific company or commercial ATS product. It only
checks a documented list of general readability factors:

* standard, recognisable section headings
* presence of contact information (email / phone)
* plain text readability (no image-only PDF)
* sensible length (word count and page count)
* excessive special characters / glyph noise
* bullet usage instead of tables and dense paragraphs
* skill keyword density
* overall section completeness

Every check returns points and a human readable message, and the final score
is the sum of earned points.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List

from backend.resume_parser import (
    OPTIONAL_SECTIONS,
    RECOMMENDED_SECTIONS,
    SECTION_LABELS,
    ParsedResume,
)

# Maximum points each check can contribute (total = 100).
MAX_POINTS = {
    "standard_headings": 22,
    "contact_information": 16,
    "readable_text": 16,
    "length": 12,
    "special_characters": 8,
    "bullet_usage": 8,
    "keyword_density": 10,
    "section_completeness": 8,
}

# Ideal resume length for a student / fresher resume.
IDEAL_WORD_RANGE = (250, 850)
IDEAL_PAGE_RANGE = (1, 2)

DISCLAIMER = (
    "ATS score is an automated readability estimate based on general "
    "formatting practices. It does not replicate any specific company or "
    "vendor ATS, and passing or failing this estimate is not a guarantee of "
    "any screening outcome."
)


@dataclass
class ATSCheck:
    """A single ATS check with the points it awarded."""

    key: str
    label: str
    score: float
    max_score: float
    status: str  # "good" | "warning" | "bad"
    message: str

    def to_dict(self) -> Dict:
        return {
            "key": self.key,
            "label": self.label,
            "score": round(self.score, 1),
            "max_score": self.max_score,
            "status": self.status,
            "message": self.message,
        }


@dataclass
class ATSReport:
    """Full ATS estimate for one resume."""

    score: float = 0.0
    checks: List[ATSCheck] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    positives: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> Dict:
        return {
            "score": round(self.score, 1),
            "checks": [check.to_dict() for check in self.checks],
            "issues": self.issues,
            "positives": self.positives,
            "suggestions": self.suggestions,
            "disclaimer": self.disclaimer,
        }


def _status(score: float, maximum: float) -> str:
    ratio = score / maximum if maximum else 0.0
    if ratio >= 0.8:
        return "good"
    if ratio >= 0.5:
        return "warning"
    return "bad"


# --------------------------------------------------------------------------
# Individual checks
# --------------------------------------------------------------------------
def check_standard_headings(resume: ParsedResume) -> ATSCheck:
    """Are the headings an ATS recognises? Standard headings score full marks."""
    maximum = MAX_POINTS["standard_headings"]
    found = resume.sections_found
    standard_found = [key for key in found if key in RECOMMENDED_SECTIONS]
    ratio = len(standard_found) / len(RECOMMENDED_SECTIONS)
    score = maximum * ratio

    if not found:
        message = (
            "No standard section headings were detected. Use headings such as "
            "Education, Skills, Experience and Projects."
        )
    elif not standard_found:
        message = (
            "No standard core headings found. Add clearly labelled sections: "
            + ", ".join(SECTION_LABELS[key] for key in RECOMMENDED_SECTIONS[:3])
            + "."
        )
    else:
        missing = [
            SECTION_LABELS[key]
            for key in RECOMMENDED_SECTIONS
            if key not in found
        ]
        if missing:
            message = (
                "Standard headings detected: "
                + ", ".join(SECTION_LABELS[key] for key in standard_found)
                + ". Missing: " + ", ".join(missing) + "."
            )
        else:
            message = "All recommended standard section headings were detected."

    return ATSCheck(
        key="standard_headings",
        label="Standard section headings",
        score=score,
        max_score=maximum,
        status=_status(score, maximum),
        message=message,
    )


def check_contact_information(resume: ParsedResume) -> ATSCheck:
    """Email and phone number are mandatory for automated screening."""
    maximum = MAX_POINTS["contact_information"]
    contact = resume.contact

    points = 0.0
    if contact.emails:
        points += maximum * 0.45
    if contact.phones:
        points += maximum * 0.35
    if contact.name:
        points += maximum * 0.20

    missing = []
    if not contact.emails:
        missing.append("email address")
    if not contact.phones:
        missing.append("phone number")
    if not contact.name:
        missing.append("candidate name")

    if not missing:
        message = "Name, email and phone number are all present."
    else:
        message = "Could not identify: " + ", ".join(missing) + "."

    return ATSCheck(
        key="contact_information",
        label="Contact information",
        score=points,
        max_score=maximum,
        status=_status(points, maximum),
        message=message,
    )


def check_readable_text(resume: ParsedResume) -> ATSCheck:
    """Text-based PDFs only - scanned images cannot be parsed by an ATS."""
    maximum = MAX_POINTS["readable_text"]
    metrics = resume.metrics
    words = metrics.get("word_count", 0)
    ratio = metrics.get("special_char_ratio", 0)

    # ratio is special chars per 1000 characters
    penalty = min(1.0, ratio / 12.0) * 0.5
    length_factor = min(1.0, words / 120.0)
    score = maximum * (0.6 * length_factor + 0.4 * (1 - penalty))

    if words < 40:
        message = (
            "Very little selectable text was extracted. This looks like an "
            "image-only PDF, which automated parsers usually cannot read."
        )
    elif ratio > 12:
        message = (
            "The text contains many special or decorative characters, which can "
            "break automated parsing. Use plain text formatting."
        )
    else:
        message = (
            f"Text layer is readable ({int(words)} words extracted). "
            "Automated parsers should be able to read this document."
        )

    return ATSCheck(
        key="readable_text",
        label="Text readability",
        score=score,
        max_score=maximum,
        status=_status(score, maximum),
        message=message,
    )


def check_length(resume: ParsedResume) -> ATSCheck:
    """One to two pages, roughly 250-850 words, is the readable sweet spot."""
    maximum = MAX_POINTS["length"]
    words = int(resume.metrics.get("word_count", 0))
    pages = int(resume.metrics.get("pages", 1) or 1)

    score = 0.0
    notes: List[str] = []

    if IDEAL_WORD_RANGE[0] <= words <= IDEAL_WORD_RANGE[1]:
        score += maximum * 0.65
    elif words < IDEAL_WORD_RANGE[0]:
        # Partial credit, less is worse the shorter it gets.
        score += maximum * 0.65 * (words / IDEAL_WORD_RANGE[0])
        notes.append(
            f"Only {words} words found - a fresher resume usually needs "
            f"at least {IDEAL_WORD_RANGE[0]}."
        )
    else:
        score += maximum * 0.65 * max(0.3, 1 - (words - IDEAL_WORD_RANGE[1]) / IDEAL_WORD_RANGE[1])
        notes.append(
            f"{words} words is quite long - consider tightening the content "
            f"to under {IDEAL_WORD_RANGE[1]} words."
        )

    if IDEAL_PAGE_RANGE[0] <= pages <= IDEAL_PAGE_RANGE[1]:
        score += maximum * 0.35
    else:
        score += maximum * 0.10
        notes.append(f"{pages} page(s) is outside the recommended 1-2 page range.")

    if not notes:
        notes.append(
            f"Length looks appropriate ({words} words across {pages} page(s))."
        )

    return ATSCheck(
        key="length",
        label="Resume length",
        score=score,
        max_score=maximum,
        status=_status(score, maximum),
        message=" ".join(notes),
    )


def check_special_characters(resume: ParsedResume) -> ATSCheck:
    """Bullet noise, symbols and decorative glyphs confuse keyword matchers."""
    maximum = MAX_POINTS["special_characters"]
    ratio = resume.metrics.get("special_char_ratio", 0)

    if ratio <= 6:
        score = maximum
        message = "Formatting is clean with very few special characters."
    elif ratio <= 12:
        score = maximum * (1 - (ratio - 6) / 12)
        message = (
            "Some decorative or special characters were found. Keep bullets "
            "simple (use '-' and avoid icons or dingbats)."
        )
    else:
        score = maximum * 0.2
        message = (
            "Excessive special formatting detected. Automated parsers often "
            "mis-read symbols, emoji and decorative bullets as text noise."
        )

    return ATSCheck(
        key="special_characters",
        label="Excessive special formatting",
        score=score,
        max_score=maximum,
        status=_status(score, maximum),
        message=message,
    )


def check_bullet_usage(resume: ParsedResume) -> ATSCheck:
    """Bullets are parsed correctly; dense paragraphs and tables are not."""
    maximum = MAX_POINTS["bullet_usage"]
    bullets = int(resume.metrics.get("bullet_count", 0))
    avg_line = resume.metrics.get("avg_line_length", 0)

    score = maximum * min(1.0, bullets / 10.0)
    if avg_line > 120:
        score *= 0.7

    if bullets >= 6:
        message = f"{bullets} bullet points detected - good structure for parsing."
    elif bullets:
        message = (
            f"Only {bullets} bullet points detected. Use bullet points instead "
            "of long paragraphs so achievements are easy to extract."
        )
    else:
        message = (
            "No bullet points detected. Convert responsibilities and "
            "achievements into short bullet points."
        )

    return ATSCheck(
        key="bullet_usage",
        label="Bullet point structure",
        score=score,
        max_score=maximum,
        status=_status(score, maximum),
        message=message,
    )


def check_keyword_density(
    resume: ParsedResume, technical_skills: List[str], role_keywords: List[str]
) -> ATSCheck:
    """
    Are role-relevant keywords actually present in the text?

    Density matters because keyword scanners look for exact words. A skill
    mentioned once in a 600 word resume has low density.
    """
    maximum = MAX_POINTS["keyword_density"]
    words = max(resume.metrics.get("word_count", 1), 1)
    target_count = len(technical_skills)

    if target_count == 0:
        score = 0.0
        message = "No known technical skills were detected in the resume text."
    else:
        # 25+ skills in a normal resume is considered full keyword coverage.
        coverage = min(1.0, target_count / 25.0)
        score = maximum * coverage
        if role_keywords:
            present = sum(1 for kw in role_keywords if kw.lower() in resume.clean_text.lower())
            score = maximum * (0.7 * coverage + 0.3 * (present / len(role_keywords)))
        message = (
            f"{target_count} technical skills detected "
            f"({round(target_count / words * 100, 1)} skill mentions per 100 words)."
        )
        if role_keywords:
            present = sum(1 for kw in role_keywords if kw.lower() in resume.clean_text.lower())
            message += (
                f" {present} of {len(role_keywords)} role keywords appear in the text."
            )

    return ATSCheck(
        key="keyword_density",
        label="Keyword presence",
        score=score,
        max_score=maximum,
        status=_status(score, maximum),
        message=message,
    )


def check_section_completeness(resume: ParsedResume) -> ATSCheck:
    """Recommended sections present = complete resume structure."""
    maximum = MAX_POINTS["section_completeness"]
    found = set(resume.sections_found)
    total = len(RECOMMENDED_SECTIONS) + len(OPTIONAL_SECTIONS)

    # Core sections count fully, optional sections count half.
    core_found = len([key for key in RECOMMENDED_SECTIONS if key in found])
    optional_found = len([key for key in OPTIONAL_SECTIONS if key in found])
    weighted = core_found + optional_found * 0.5

    score = maximum * min(1.0, weighted / total)

    missing_core = [
        SECTION_LABELS[key] for key in RECOMMENDED_SECTIONS if key not in found
    ]
    if missing_core:
        message = "Missing recommended section(s): " + ", ".join(missing_core) + "."
    else:
        message = "All recommended sections are present."

    return ATSCheck(
        key="section_completeness",
        label="Section completeness",
        score=score,
        max_score=maximum,
        status=_status(score, maximum),
        message=message,
    )


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------
def analyze_ats(
    resume: ParsedResume,
    technical_skills: List[str],
    role_keywords: List[str] | None = None,
) -> ATSReport:
    """Run every ATS check and aggregate the estimate."""
    report = ATSReport()
    report.checks = [
        check_standard_headings(resume),
        check_contact_information(resume),
        check_readable_text(resume),
        check_length(resume),
        check_special_characters(resume),
        check_bullet_usage(resume),
        check_keyword_density(resume, technical_skills, role_keywords or []),
        check_section_completeness(resume),
    ]

    report.score = sum(check.score for check in report.checks)
    report.score = max(0.0, min(100.0, report.score))

    for check in report.checks:
        if check.status == "good":
            report.positives.append(f"{check.label}: {check.message}")
        else:
            report.issues.append(f"{check.label}: {check.message}")
        if check.status != "good":
            report.suggestions.append(_suggestion_for(check))

    return report


def _suggestion_for(check: ATSCheck) -> str:
    """Actionable advice for a failing check."""
    suggestions = {
        "standard_headings": (
            "Rename your headings to standard names (Objective / Summary, "
            "Education, Skills, Experience, Projects) so an automated parser "
            "can find them."
        ),
        "contact_information": (
            "Add a plain-text email address and phone number near the top of "
            "the first page."
        ),
        "readable_text": (
            "Export the resume as a text-based PDF. Do not upload a scanned "
            "photo or screenshot of a resume."
        ),
        "length": (
            "Aim for 1-2 pages and roughly 300-800 words. Remove repeated or "
            "irrelevant content."
        ),
        "special_characters": (
            "Replace icons, emoji and decorative bullets with a simple "
            "hyphen (-) or a plain bullet character."
        ),
        "bullet_usage": (
            "Rewrite responsibilities as short bullet points starting with a "
            "strong action verb."
        ),
        "keyword_density": (
            "Mention the exact tools and technologies you used (for example "
            "'Python', 'MySQL') instead of only describing them in general terms."
        ),
        "section_completeness": (
            "Add the missing sections with clear headings. A fresher resume "
            "should at least contain Summary, Education, Skills, Experience "
            "and Projects."
        ),
    }
    return suggestions.get(check.key, check.message)


def ats_score_breakdown(resume: ParsedResume, technical_skills: List[str]) -> Dict:
    """Convenience helper used by the API layer / tests."""
    report = analyze_ats(resume, technical_skills)
    return {
        "score": report.score,
        "checks": [check.to_dict() for check in report.checks],
        "issues": report.issues,
        "positives": report.positives,
    }