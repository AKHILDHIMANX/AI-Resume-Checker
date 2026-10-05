"""
Job role matching.

The matcher compares a resume against a target role defined in
``data/job_roles.json`` and reports *similarity only*. It never states that a
candidate is qualified or unqualified for a job.

Two independent signals are combined:

1. **Weighted skill coverage** - core / preferred / bonus skills of the role,
   each weighted 3 / 2 / 1.
2. **TF-IDF cosine similarity** between the resume text and a role profile
   text (role name, summary, responsibilities and keywords).

The final ``job_match_score`` is a transparent weighted blend of both.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional

from backend.skill_extractor import find_technical_skills, _pattern_for

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
JOBS_FILE = os.path.join(DATA_DIR, "job_roles.json")

CORE_WEIGHT = 3.0
PREFERRED_WEIGHT = 2.0
BONUS_WEIGHT = 1.0

# Blend of the two similarity signals used for the headline number.
SKILL_SIGNAL_WEIGHT = 0.65
TEXT_SIGNAL_WEIGHT = 0.35


class UnknownRoleError(Exception):
    """Raised when the requested job role is not present in the dataset."""


class JobDataError(RuntimeError):
    """Raised when ``data/job_roles.json`` is missing or malformed."""


# --------------------------------------------------------------------------
# Dataset access
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_job_roles() -> List[Dict]:
    if not os.path.exists(JOBS_FILE):
        raise JobDataError(f"Job role dataset not found at: {JOBS_FILE}")
    try:
        with open(JOBS_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise JobDataError(f"Job role dataset is not valid JSON: {exc}") from exc

    roles = data.get("roles")
    if not roles:
        raise JobDataError("Job role dataset contains no roles.")
    return roles


@lru_cache(maxsize=1)
def _alias_index() -> Dict[str, str]:
    """Map every role name and alias (lowercase) to the canonical role name."""
    index: Dict[str, str] = {}
    for entry in load_job_roles():
        canonical = entry["role"]
        index[canonical.lower()] = canonical
        for alias in entry.get("aliases", []):
            index[alias.strip().lower()] = canonical
    return index


def list_roles() -> List[Dict]:
    """Return ``[{'role':..., 'category':..., 'summary':...}, ...]`` for the UI."""
    return [
        {
            "role": entry["role"],
            "category": entry.get("category", "General"),
            "summary": entry.get("summary", ""),
        }
        for entry in load_job_roles()
    ]


def normalise_role(role: str) -> str:
    """
    Resolve user input to a canonical role name.

    Matching is case-insensitive and tolerates extra whitespace. When nothing
    matches exactly, a fuzzy fallback picks the closest role name so the app
    never crashes on a slightly different spelling.
    """
    index = _alias_index()
    cleaned = re.sub(r"\s+", " ", (role or "").strip().lower())

    if not cleaned:
        raise UnknownRoleError("No job role was provided.")

    if cleaned in index:
        return index[cleaned]

    # "data analyst role" / "job: data analyst"
    stripped = re.sub(r"\b(job|role|position|title|opening)\b\s*:?\s*", " ", cleaned).strip()
    stripped = re.sub(r"\s+", " ", stripped)
    if stripped in index:
        return index[stripped]

    for key, canonical in index.items():
        if len(key) >= 4 and (key in stripped or stripped in key):
            return canonical

    raise UnknownRoleError(
        f"'{role}' is not one of the available job roles. "
        "Please pick a role from the list."
    )


def get_role(role_name: str) -> Dict:
    canonical = normalise_role(role_name)
    for entry in load_job_roles():
        if entry["role"] == canonical:
            return entry
    raise UnknownRoleError(f"Role '{role_name}' could not be loaded.")


# --------------------------------------------------------------------------
# Result container
# --------------------------------------------------------------------------
@dataclass
class JobMatchResult:
    """Similarity report between a resume and one target role."""

    role: str
    role_category: str = ""
    role_summary: str = ""
    match_score: float = 0.0
    skill_coverage_score: float = 0.0
    text_similarity_score: float = 0.0
    matched_core: List[str] = field(default_factory=list)
    matched_preferred: List[str] = field(default_factory=list)
    matched_bonus: List[str] = field(default_factory=list)
    missing_core: List[str] = field(default_factory=list)
    missing_preferred: List[str] = field(default_factory=list)
    missing_bonus: List[str] = field(default_factory=list)
    matched_keywords: List[str] = field(default_factory=list)
    missing_keywords: List[str] = field(default_factory=list)
    unexpected_skills: List[str] = field(default_factory=list)
    responsibilities: List[str] = field(default_factory=list)
    explanation: str = ""

    @property
    def matched_skills(self) -> List[str]:
        """All matched skills, de-duplicated and order preserved."""
        return list(dict.fromkeys(
            self.matched_core + self.matched_preferred + self.matched_bonus
        ))

    def to_dict(self) -> Dict:
        return {
            "role": self.role,
            "role_category": self.role_category,
            "role_summary": self.role_summary,
            "match_score": round(self.match_score, 1),
            "skill_coverage_score": round(self.skill_coverage_score, 1),
            "text_similarity_score": round(self.text_similarity_score, 1),
            "matched_skills": self.matched_skills,
            "matched_core": self.matched_core,
            "matched_preferred": self.matched_preferred,
            "matched_bonus": self.matched_bonus,
            "missing_core": self.missing_core,
            "missing_preferred": self.missing_preferred,
            "missing_bonus": self.missing_bonus,
            "missing_skills": self.missing_core + self.missing_preferred + self.missing_bonus,
            "matched_keywords": self.matched_keywords,
            "missing_keywords": self.missing_keywords,
            "unexpected_skills": self.unexpected_skills,
            "responsibilities": self.responsibilities,
            "explanation": self.explanation,
        }


# --------------------------------------------------------------------------
# Signal 1: weighted skill coverage
# --------------------------------------------------------------------------
def _normalise_skill_name(skill: str) -> str:
    """
    Canonical lookup key for a role skill.

    A role may legitimately list the same technology twice under different
    spellings (for example "REST API" as a core skill and as a bonus skill).
    This helper collapses the obvious variants so the role's total weight is
    counted only once and the matched/missing lists cannot contain the same
    skill twice.
    """
    name = skill.lower().strip()
    name = name.replace("scikit-learn", "scikit learn")
    name = name.replace("scikit learn", "sklearn")
    name = name.replace("restful api", "rest api")
    name = name.replace("node js", "node.js")
    name = name.replace("reactjs", "react")
    return re.sub(r"\s+", " ", name)


def _dedupe_role_skills(skills: List[str]) -> List[str]:
    """Drop aliases and exact duplicates while preserving first spelling."""
    seen: set = set()
    result: List[str] = []
    for skill in skills:
        key = _normalise_skill_name(skill)
        if key in seen:
            continue
        seen.add(key)
        result.append(skill)
    return result


def _dedupe_across_buckets(buckets: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """
    Make every role skill belong to exactly one importance tier.

    A dataset entry may repeat a skill in two tiers (for example "REST API"
    listed as both core and bonus). Counting it twice would inflate the
    denominator of the coverage score and show the same gap twice in the
    report, so each skill is kept only in the highest tier it appears in:
    core beats preferred beats bonus.
    """
    seen: set = set()
    cleaned: Dict[str, List[str]] = {}
    for name in ("core", "preferred", "bonus"):
        kept: List[str] = []
        for skill in buckets.get(name, []):
            key = _normalise_skill_name(skill)
            if key in seen:
                continue
            seen.add(key)
            kept.append(skill)
        cleaned[name] = kept
    return cleaned


def _split_skills(resume_text: str, buckets: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Split every role skill bucket into matched / missing lists."""
    by_category = find_technical_skills(resume_text)
    detected = {skill.lower(): skill for skills in by_category.values() for skill in skills}

    result: Dict[str, List[str]] = {}
    for name, skills in buckets.items():
        matched, missing = [], []
        for skill in skills:
            canonical = detected.get(skill.lower())
            if canonical:
                matched.append(canonical)
            else:
                missing.append(skill)
        result[f"{name}_matched"] = matched
        result[f"{name}_missing"] = missing
    return result


def score_skill_coverage(resume_text: str, role: Dict) -> Dict:
    """
    Weighted skill coverage of a role by a resume.

    score = 100 * (weighted hits / total role weight)

    A resume with **more** skills than the role does not score above 100 -
    this is a coverage measure, not a "skill stuffing" reward.
    """
    buckets = _dedupe_across_buckets(
        {
            "core": _dedupe_role_skills(list(role.get("core_skills", []))),
            "preferred": _dedupe_role_skills(list(role.get("preferred_skills", []))),
            "bonus": _dedupe_role_skills(list(role.get("bonus_skills", []))),
        }
    )
    weights = {"core": CORE_WEIGHT, "preferred": PREFERRED_WEIGHT, "bonus": BONUS_WEIGHT}

    split = _split_skills(resume_text, buckets)

    earned = 0.0
    possible = 0.0
    for name, skills in buckets.items():
        possible += weights[name] * len(skills)
        earned += weights[name] * len(split[f"{name}_matched"])

    score = (earned / possible * 100) if possible else 0.0
    return {"score": round(score, 1), **split}


# --------------------------------------------------------------------------
# Signal 2: TF-IDF cosine similarity
# --------------------------------------------------------------------------
def _role_profile_text(role: Dict) -> str:
    """Flatten a role definition into a document for TF-IDF comparison."""
    parts: List[str] = [
        role.get("role", ""),
        role.get("role", ""),
        role.get("category", ""),
        role.get("summary", ""),
    ]
    parts.extend(role.get("core_skills", []))
    parts.extend(role.get("preferred_skills", []))
    parts.extend(role.get("responsibilities", []))
    parts.extend(role.get("keywords", []))
    return " ".join(part for part in parts if part)


@lru_cache(maxsize=32)
def _role_profile_cached(role_name: str) -> str:
    return _role_profile_text(get_role(role_name))


def text_similarity(resume_text: str, role_name: str) -> float:
    """
    TF-IDF cosine similarity between resume text and the role profile.

    Returns a value from 0 to 100. Falls back to a token-overlap ratio when
    scikit-learn is unavailable or the resume is too short to vectorise.
    """
    profile = _role_profile_cached(role_name)

    if not resume_text.strip() or not profile.strip():
        return 0.0

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:  # pragma: no cover
        return _jaccard_overlap(resume_text, profile)

    corpus = [resume_text, profile]
    try:
        vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
            max_features=6000,
            token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9+#.\-]{1,}\b",
        )
        matrix = vectorizer.fit_transform(corpus)
        if matrix.shape[1] == 0:
            return _jaccard_overlap(resume_text, profile)
        score = cosine_similarity(matrix[0], matrix[1])[0][0]
    except ValueError:
        return _jaccard_overlap(resume_text, profile)

    return round(float(score) * 100, 1)


def _jaccard_overlap(a: str, b: str) -> float:
    """Fallback similarity based on shared vocabulary."""
    token_a = set(re.findall(r"[a-z][a-z0-9+#]{1,}", a.lower()))
    token_b = set(re.findall(r"[a-z][a-z0-9+#]{1,}", b.lower()))
    if not token_a or not token_b:
        return 0.0
    return round(len(token_a & token_b) / len(token_a | token_b) * 100, 1)


# --------------------------------------------------------------------------
# Keyword coverage
# --------------------------------------------------------------------------
def analyse_keywords(resume_text: str, role: Dict, limit: int = 10) -> Dict[str, List[str]]:
    """Split role keywords into present / absent ones."""
    present, absent = [], []
    for keyword in role.get("keywords", []):
        if re.search(rf"(?<![a-z0-9]){re.escape(keyword.lower())}(?![a-z0-9])", resume_text.lower()):
            present.append(keyword)
        else:
            absent.append(keyword)
    return {"matched": present[:limit], "missing": absent[:limit]}


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------
def match_job(
    resume_text: str,
    role_name: str,
    resume_skills: Optional[List[str]] = None,
) -> JobMatchResult:
    """
    Compare a resume with a target job role.

    Args:
        resume_text: cleaned resume text
        role_name: any role name / alias from ``data/job_roles.json``
        resume_skills: technical skills already detected (avoids re-scanning)

    Raises:
        UnknownRoleError: role is not part of the dataset
    """
    role = get_role(role_name)
    coverage = score_skill_coverage(resume_text, role)
    text_score = text_similarity(resume_text, role["role"])

    combined = (
        SKILL_SIGNAL_WEIGHT * coverage["score"] + TEXT_SIGNAL_WEIGHT * text_score
    )
    combined = max(0.0, min(100.0, combined))

    keywords = analyse_keywords(resume_text, role)
    detected = resume_skills if resume_skills is not None else [
        skill for skills in find_technical_skills(resume_text).values() for skill in skills
    ]
    role_skill_pool = set()
    for bucket in ("core_skills", "preferred_skills", "bonus_skills"):
        role_skill_pool.update(role.get(bucket, []))
    unexpected = [s for s in detected if s not in role_skill_pool]

    result = JobMatchResult(
        role=role["role"],
        role_category=role.get("category", ""),
        role_summary=role.get("summary", ""),
        match_score=round(combined, 1),
        skill_coverage_score=coverage["score"],
        text_similarity_score=text_score,
        matched_core=coverage["core_matched"],
        matched_preferred=coverage["preferred_matched"],
        matched_bonus=coverage["bonus_matched"],
        missing_core=coverage["core_missing"],
        missing_preferred=coverage["preferred_missing"],
        missing_bonus=coverage["bonus_missing"],
        matched_keywords=keywords["matched"],
        missing_keywords=keywords["missing"],
        unexpected_skills=unexpected,
        responsibilities=role.get("responsibilities", []),
    )
    result.explanation = _explain(result)
    return result


def _explain(result: JobMatchResult) -> str:
    """One honest sentence describing how the score was produced."""
    total_skills = len(result.matched_skills)
    role_total = total_skills + sum(
        len(bucket) for bucket in (result.missing_core, result.missing_preferred,
                                   result.missing_bonus)
    )
    return (
        f"Resume-to-role similarity of {result.match_score:.1f}/100 for "
        f"'{result.role}'. This is an automated text and skill comparison "
        f"({total_skills} of {role_total} role skills matched, "
        f"TF-IDF text similarity {result.text_similarity_score:.1f}/100). "
        f"It indicates keyword overlap only - it is not a judgement of the "
        f"candidate's ability or suitability for the role."
    )


def rank_roles(resume_text: str, top_n: int | None = None) -> List[Dict]:
    """
    Rank every dataset role against the resume, best match first.

    Used by the "role fit overview" chart on the dashboard. ``top_n=None``
    returns the full ranking; pass an integer to truncate it.
    """
    scores: List[Dict] = []
    for entry in load_job_roles():
        coverage = score_skill_coverage(resume_text, entry)["score"]
        text_score = text_similarity(resume_text, entry["role"])
        combined = max(
            0.0, min(100.0, SKILL_SIGNAL_WEIGHT * coverage + TEXT_SIGNAL_WEIGHT * text_score)
        )
        scores.append(
            {
                "role": entry["role"],
                "category": entry.get("category", ""),
                "score": round(combined, 1),
                "skill_coverage": coverage,
                "text_similarity": text_score,
            }
        )
    scores.sort(key=lambda item: (-item["score"], item["role"]))
    return scores if top_n is None else scores[:top_n]