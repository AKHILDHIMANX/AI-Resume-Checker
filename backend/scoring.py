"""
Transparent scoring.

Every score below is derived from the parsed resume - nothing is random.

    Overall Score = 0.30 * Structure
                  + 0.25 * Content
                  + 0.25 * Skills
                  + 0.20 * ATS

``Job Match`` is reported separately (and shown as its own card) because it
only makes sense relative to a chosen target role.

Each component is itself a weighted sum of small, individually reported
sub-checks, so the dashboard can always explain *why* a score came out the way
it did.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from backend.resume_parser import (
    OPTIONAL_SECTIONS,
    RECOMMENDED_SECTIONS,
    SECTION_LABELS,
    ParsedResume,
)
from backend.skill_extractor import SkillProfile

# --------------------------------------------------------------------------
# Overall weighting (must sum to 1.0)
# --------------------------------------------------------------------------
OVERALL_WEIGHTS = {
    "structure": 0.30,
    "content": 0.25,
    "skills": 0.25,
    "ats": 0.20,
}

# Sub-weights per component (each list must sum to 1.0)
STRUCTURE_WEIGHTS = {
    "sections": 0.40,
    "contact": 0.25,
    "headings": 0.20,
    "organisation": 0.15,
}

CONTENT_WEIGHTS = {
    "length": 0.25,
    "action_verbs": 0.25,
    "quantified": 0.20,
    "detail_level": 0.20,
    "filler": 0.10,
}

SKILLS_WEIGHTS = {
    "breadth": 0.35,
    "technical_share": 0.30,
    "soft_skills": 0.15,
    "keyword_strength": 0.20,
}

# Targets used by the sub-checks
TARGET_SKILLS_FOR_BREADTH = 18
TARGET_SOFT_SKILLS = 5
TARGET_QUANTIFIERS = 4
IDEAL_WORDS = (300, 800)


@dataclass
class ComponentScore:
    """One scored component with its sub-checks."""

    key: str
    label: str
    score: float
    weight: float
    breakdown: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "key": self.key,
            "label": self.label,
            "score": round(self.score, 1),
            "weight": self.weight,
            "breakdown": self.breakdown,
        }


@dataclass
class ScoreReport:
    """All scores produced for one resume."""

    overall: float = 0.0
    components: List[ComponentScore] = field(default_factory=list)
    grading: str = ""
    weights: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "overall": round(self.overall, 1),
            "grade": self.grading,
            "components": [component.to_dict() for component in self.components],
            "weights": self.weights,
        }

    def component(self, key: str) -> float:
        for item in self.components:
            if item.key == key:
                return item.score
        return 0.0


def _ratio_score(value: float, target: float) -> float:
    """0-100 score that reaches 100 at ``target``."""
    if target <= 0:
        return 0.0
    return max(0.0, min(100.0, (value / target) * 100))


def grade_for(score: float) -> str:
    """Plain-English band for a 0-100 score."""
    if score >= 90:
        return "Excellent"
    if score >= 80:
        return "Very Good"
    if score >= 70:
        return "Good"
    if score >= 60:
        return "Needs Improvement"
    if score >= 40:
        return "Weak"
    return "Very Weak"


# --------------------------------------------------------------------------
# Component: Structure
# --------------------------------------------------------------------------
def score_structure(resume: ParsedResume) -> ComponentScore:
    """Section coverage, contact block, heading style, overall organisation."""
    found = set(resume.sections_found)
    breakdown: List[Dict] = []

    # 1. Recommended + optional sections present
    core_present = [key for key in RECOMMENDED_SECTIONS if key in found]
    optional_present = [key for key in OPTIONAL_SECTIONS if key in found]
    total_possible = len(RECOMMENDED_SECTIONS) + len(OPTIONAL_SECTIONS) * 0.5
    earned = len(core_present) + len(optional_present) * 0.5
    sections_score = max(0.0, min(100.0, earned / total_possible * 100))
    breakdown.append(
        {
            "label": "Sections present",
            "score": round(sections_score, 1),
            "detail": f"{len(core_present)}/{len(RECOMMENDED_SECTIONS)} core and "
            f"{len(optional_present)}/{len(OPTIONAL_SECTIONS)} optional sections found",
        }
    )

    # 2. Contact completeness
    contact_score = float(resume.contact.completeness)
    missing_contact = []
    if not resume.contact.emails:
        missing_contact.append("email")
    if not resume.contact.phones:
        missing_contact.append("phone")
    if not resume.contact.name:
        missing_contact.append("name")
    breakdown.append(
        {
            "label": "Contact information",
            "score": contact_score,
            "detail": "missing: " + ", ".join(missing_contact)
            if missing_contact
            else "email, phone and name all detected",
        }
    )

    # 3. Standard headings - are section names conventional?
    conventional = sum(
        1 for key in resume.sections_found if key in RECOMMENDED_SECTIONS + OPTIONAL_SECTIONS
    )
    heading_score = _ratio_score(conventional, len(RECOMMENDED_SECTIONS))
    breakdown.append(
        {
            "label": "Standard headings",
            "score": round(heading_score, 1),
            "detail": f"{conventional} conventional heading(s) detected",
        }
    )

    # 4. Organisation - bullet usage and non-empty line density
    bullets = resume.metrics.get("bullet_count", 0)
    non_empty = resume.metrics.get("non_empty_lines", 1) or 1
    org_score = max(
        0.0,
        min(100.0, 0.6 * _ratio_score(bullets, 8) + 0.4 * min(100.0, non_empty * 4)),
    )
    breakdown.append(
        {
            "label": "Content organisation",
            "score": round(org_score, 1),
            "detail": f"{int(bullets)} bullet point(s) across {int(non_empty)} text lines",
        }
    )

    score = (
        STRUCTURE_WEIGHTS["sections"] * sections_score
        + STRUCTURE_WEIGHTS["contact"] * contact_score
        + STRUCTURE_WEIGHTS["headings"] * heading_score
        + STRUCTURE_WEIGHTS["organisation"] * org_score
    )

    return ComponentScore(
        key="structure",
        label="Structure Score",
        score=score,
        weight=OVERALL_WEIGHTS["structure"],
        breakdown=breakdown,
    )


# --------------------------------------------------------------------------
# Component: Content quality
# --------------------------------------------------------------------------
def score_content(resume: ParsedResume, profile: SkillProfile) -> ComponentScore:
    """Length, action verbs, measurable results, detail level, filler words."""
    breakdown: List[Dict] = []
    words = resume.metrics.get("word_count", 0)

    # 1. Length
    if IDEAL_WORDS[0] <= words <= IDEAL_WORDS[1]:
        length_score = 100.0
    elif words < IDEAL_WORDS[0]:
        length_score = max(0.0, _ratio_score(words, IDEAL_WORDS[0]) * 0.9)
    else:
        overage = words - IDEAL_WORDS[1]
        length_score = max(0.0, 100.0 - overage / 10)
    breakdown.append(
        {
            "label": "Content length",
            "score": round(length_score, 1),
            "detail": f"{int(words)} words (recommended {IDEAL_WORDS[0]}-{IDEAL_WORDS[1]})",
        }
    )

    # 2. Action verbs
    verb_score = _ratio_score(len(profile.action_verbs), 8)
    breakdown.append(
        {
            "label": "Action verbs",
            "score": round(verb_score, 1),
            "detail": f"{len(profile.action_verbs)} distinct action verbs used",
        }
    )

    # 3. Quantified results
    quant_score = _ratio_score(profile.quantifier_count, TARGET_QUANTIFIERS)
    breakdown.append(
        {
            "label": "Measurable results",
            "score": round(quant_score, 1),
            "detail": f"{profile.quantifier_count} numbers, percentages or volumes found",
        }
    )

    # 4. Detail level - average sentence / line length in a readable band
    avg_sentence = resume.metrics.get("avg_sentence_length", 0)
    if 0 < avg_sentence <= 25:
        detail_score = 100.0
    elif avg_sentence > 25:
        detail_score = max(30.0, 100.0 - (avg_sentence - 25) * 2)
    else:
        detail_score = 50.0
    breakdown.append(
        {
            "label": "Sentence readability",
            "score": round(detail_score, 1),
            "detail": f"average sentence length {avg_sentence} words",
        }
    )

    # 5. Filler phrases (fewer is better)
    filler_score = max(0.0, 100.0 - profile.filler_count * 12)
    breakdown.append(
        {
            "label": "Vague phrasing",
            "score": round(filler_score, 1),
            "detail": f"{profile.filler_count} vague phrase(s) such as 'responsible for' or 'etc.'",
        }
    )

    score = (
        CONTENT_WEIGHTS["length"] * length_score
        + CONTENT_WEIGHTS["action_verbs"] * verb_score
        + CONTENT_WEIGHTS["quantified"] * quant_score
        + CONTENT_WEIGHTS["detail_level"] * detail_score
        + CONTENT_WEIGHTS["filler"] * filler_score
    )

    return ComponentScore(
        key="content",
        label="Content Score",
        score=score,
        weight=OVERALL_WEIGHTS["content"],
        breakdown=breakdown,
    )


# --------------------------------------------------------------------------
# Component: Skills
# --------------------------------------------------------------------------
def score_skills(profile: SkillProfile, resume: ParsedResume) -> ComponentScore:
    """Breadth of technical skills, technical/soft balance, keyword strength."""
    breakdown: List[Dict] = []

    technical_count = len(profile.technical)
    soft_count = len(profile.soft)

    # 1. Breadth
    breadth_score = _ratio_score(technical_count, TARGET_SKILLS_FOR_BREADTH)
    breakdown.append(
        {
            "label": "Technical skill breadth",
            "score": round(breadth_score, 1),
            "detail": f"{technical_count} technical skills detected "
            f"(target {TARGET_SKILLS_FOR_BREADTH})",
        }
    )

    # 2. Technical share - are claims backed by named technologies?
    named = profile.total_matches
    words = max(resume.metrics.get("word_count", 1), 1)
    repetition = named / words * 100  # skill mentions per 100 words
    share_score = max(0.0, min(100.0, repetition / 12.0 * 100))
    breakdown.append(
        {
            "label": "Skill specificity",
            "score": round(share_score, 1),
            "detail": f"{named} skill mentions in {int(words)} words "
            f"({round(repetition, 1)} per 100 words)",
        }
    )

    # 3. Soft skills
    soft_score = _ratio_score(soft_count, TARGET_SOFT_SKILLS)
    breakdown.append(
        {
            "label": "Soft skills",
            "score": round(soft_score, 1),
            "detail": f"{soft_count} soft skills detected (target {TARGET_SOFT_SKILLS})",
        }
    )

    # 4. Keyword strength from the TF-IDF extraction
    top_score = profile.keywords[0]["score"] if profile.keywords else 0.0
    keyword_score = max(0.0, min(100.0, top_score / 0.16 * 100))
    breakdown.append(
        {
            "label": "Keyword strength",
            "score": round(keyword_score, 1),
            "detail": f"top TF-IDF keyword weight {round(top_score, 4)}",
        }
    )

    score = (
        SKILLS_WEIGHTS["breadth"] * breadth_score
        + SKILLS_WEIGHTS["technical_share"] * share_score
        + SKILLS_WEIGHTS["soft_skills"] * soft_score
        + SKILLS_WEIGHTS["keyword_strength"] * keyword_score
    )

    return ComponentScore(
        key="skills",
        label="Skills Score",
        score=score,
        weight=OVERALL_WEIGHTS["skills"],
        breakdown=breakdown,
    )


# --------------------------------------------------------------------------
# Component: ATS estimate
# --------------------------------------------------------------------------
def score_ats(ats_score: float) -> ComponentScore:
    """Wrap the ATS analyzer output as a scored component."""
    return ComponentScore(
        key="ats",
        label="ATS Score",
        score=ats_score,
        weight=OVERALL_WEIGHTS["ats"],
        breakdown=[
            {
                "label": "ATS compatibility estimate",
                "score": round(ats_score, 1),
                "detail": "computed by backend/ats_analyzer.py",
            }
        ],
    )


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------
def calculate_scores(
    resume: ParsedResume,
    profile: SkillProfile,
    ats_score: float,
    job_match_score: float | None = None,
) -> ScoreReport:
    """
    Build the full score report.

    Args:
        resume: parsed resume
        profile: extracted skill profile
        ats_score: 0-100 ATS estimate from ``ats_analyzer``
        job_match_score: optional role similarity, reported separately
    """
    structure = score_structure(resume)
    content = score_content(resume, profile)
    skills = score_skills(profile, resume)
    ats = score_ats(ats_score)

    report = ScoreReport(
        components=[structure, content, skills, ats],
        weights=dict(OVERALL_WEIGHTS),
    )
    report.overall = sum(component.score * component.weight for component in report.components)
    report.overall = max(0.0, min(100.0, report.overall))
    report.grading = grade_for(report.overall)

    return report


def missing_section_labels(resume: ParsedResume) -> List[Dict]:
    """Recommended sections that were not detected, with a friendly reason."""
    found = set(resume.sections_found)
    reasons = {
        "summary": "A 2-3 line summary tells the reader what you are looking for.",
        "education": "Recruiters look for degree, institution and year of passing.",
        "skills": "A dedicated skills section makes keyword matching far easier.",
        "experience": "Add internships, freelance work or academic projects here.",
        "projects": "Projects are the strongest proof of practical ability for freshers.",
    }

    result: List[Dict] = []
    for key in RECOMMENDED_SECTIONS:
        if key not in found:
            result.append(
                {
                    "key": key,
                    "label": SECTION_LABELS[key],
                    "importance": "Recommended",
                    "reason": reasons.get(key, "This section strengthens the resume."),
                }
            )
    return result


def optional_section_labels(resume: ParsedResume) -> List[Dict]:
    """Optional sections that are not present (reported, not penalised)."""
    found = set(resume.sections_found)
    reasons = {
        "certifications": "Courses and certificates show continuous learning.",
        "achievements": "Awards, competitions and academic honours add credibility.",
        "languages": "Language skills are useful for communication-heavy roles.",
        "interests": "Interests give a short, human introduction to your profile.",
        "references": "Some recruiters still ask for references - keep them ready.",
    }
    return [
        {
            "key": key,
            "label": SECTION_LABELS[key],
            "reason": reasons.get(key, ""),
        }
        for key in OPTIONAL_SECTIONS
        if key not in found
    ]