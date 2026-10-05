"""
Skill extraction.

Turns the cleaned resume text into a structured skill profile:

* technical skills grouped by category (Programming, Web, Database, ...)
* soft skills
* keyword extraction (TF-IDF over the resume)
* unigrams + bigrams frequency analysis
* action verbs / quantified-achievement signals used by the content score

Matching is done with word-boundary aware regular expressions so that
"C" does not match inside "C++" or "C#" and "Go" does not match "Google".
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Set, Tuple

from backend.skill_data import all_aliases, soft_skills, technical_skills

# --------------------------------------------------------------------------
# Word-boundary helpers
# --------------------------------------------------------------------------
# Characters that must not sit directly next to a skill match. Keeping '.' out
# of the class means "Node.js." at the end of a sentence still matches, while
# '+' and '#' protect "C" from matching inside "C++" / "C#".
_BOUNDARY = r"0-9a-zA-Z+#"


def _pattern_for(term: str) -> re.Pattern:
    """Build a boundary-safe regex for a skill term."""
    escaped = re.escape(term.strip())
    # allow flexible internal whitespace: "Power  BI" == "Power BI"
    escaped = re.sub(r"(?<!\\)\\ (?!\\)", r"\\s+", escaped)
    left = rf"(?<![{_BOUNDARY}])"
    right = rf"(?![{_BOUNDARY}])"
    return re.compile(left + escaped + right, re.IGNORECASE)


# Longest terms first so "Machine Learning" wins over "Learning".
def _build_patterns(terms: Iterable[str]) -> List[Tuple[str, re.Pattern]]:
    unique = sorted({t.strip() for t in terms if t and t.strip()},
                    key=lambda t: (-len(t), t.lower()))
    return [(term, _pattern_for(term)) for term in unique]


_TECH_PATTERNS = _build_patterns(
    {skill for skills in technical_skills().values() for skill in skills}
)
_SOFT_PATTERNS = _build_patterns(soft_skills())

# Aliases shorter than three characters ("c", "js", "ai") risk matching inside
# unrelated words, so only the unambiguous ones are enabled. Every pattern is
# still boundary-safe, so "js" cannot match inside "jsoup" or "jobs".
_SHORT_ALIASES = {"c", "r", "js"}
_ALIAS_PATTERNS = _build_patterns(
    alias for alias in all_aliases()
    if len(alias) >= 3 or alias in _SHORT_ALIASES
)


# --------------------------------------------------------------------------
# Action verbs / achievement signals
# --------------------------------------------------------------------------
ACTION_VERBS = {
    "achieved", "architected", "automated", "built", "collaborated", "completed",
    "conducted", "created", "debugged", "deployed", "designed", "developed",
    "enhanced", "established", "evaluated", "executed", "generated", "implemented",
    "improved", "increased", "integrated", "launched", "led", "maintained",
    "managed", "migrated", "modelled", "modeled", "optimised", "optimized",
    "orchestrated", "performed", "prepared", "presented", "reduced", "refactored",
    "resolved", "reviewed", "scaled", "scheduled", "streamlined", "tested",
    "trained", "troubleshot", "upgraded", "won", "wrote", "analysed", "analyzed",
    "configured", "documented", "initiated", "spearheaded", "standardised",
    "standardized", "benchmarked", "engineered", "delivered", "compiled",
    "debugging", "developed", "responsible", "owned", "coordinated",
}

# --------------------------------------------------------------------------
# Measurable-result signals
# --------------------------------------------------------------------------
QUANTIFIER_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s?(?:%|per\s?cent\b|pct)"
    r"|\b\d+(?:\.\d+)?\s?(?:k|m|lakh|lac|crore|cr|billion|million)\b"
    r"|\b\d{1,3}(?:,\d{3})+\b"
    r"|\b\d{2,}\+?\b(?:\s+\w+){0,2}\s+"
    r"(?:users?|clients?|records?|rows?|students?|requests?|queries|queries|"
    r"files?|items?|hours?|days?|weeks?|months?|years?|candidates?|"
    r"employees?|transactions?|datasets?|reports?|tickets?|orders?|products?)\b"
    r"|\b\d+(?:\.\d+)?\s?(?:x|times)\s+(?:faster|slower|more|less)\b"
    r"|\b(?:rs\.?\s?|inr\s?|usd\s?|eur\s?|₹|\$|€)\s?\d"
)

FILLER_WORDS = {
    "responsible", "duties", "assigned", "various", "various tasks", "etc",
    "etc.", "helped", "assisted", "participated", "involved", "worked",
}


# --------------------------------------------------------------------------
# Result containers
# --------------------------------------------------------------------------
@dataclass
class SkillProfile:
    """Structured view of every skill found in a resume."""

    technical: List[str] = field(default_factory=list)
    technical_by_category: Dict[str, List[str]] = field(default_factory=dict)
    soft: List[str] = field(default_factory=list)
    keywords: List[Dict] = field(default_factory=list)
    frequent_terms: List[Dict] = field(default_factory=list)
    action_verbs: List[str] = field(default_factory=list)
    quantifier_count: int = 0
    filler_count: int = 0
    total_matches: int = 0
    skill_to_category: Dict[str, str] = field(default_factory=dict)
    source_sections: Dict[str, str] = field(default_factory=dict)
    aliases_detected: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "technical": self.technical,
            "technical_by_category": self.technical_by_category,
            "soft": self.soft,
            "aliases_detected": self.aliases_detected,
            "keywords": self.keywords,
            "frequent_terms": self.frequent_terms,
            "action_verbs": self.action_verbs,
            "quantifier_count": self.quantifier_count,
            "filler_count": self.filler_count,
            "total_matches": self.total_matches,
            "skill_to_category": self.skill_to_category,
            "source_sections": self.source_sections,
        }

    @property
    def category_counts(self) -> Dict[str, int]:
        return {name: len(skills) for name, skills in self.technical_by_category.items()}


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def find_technical_skills(text: str) -> Dict[str, List[str]]:
    """
    Return ``{category: [matched skills]}`` for every technical category.

    A skill is only reported once even if it matches several times.
    """
    if not text:
        return {}

    categories = technical_skills()
    found: Dict[str, List[str]] = {}

    for category, skills in categories.items():
        matches: List[str] = []
        for skill in skills:
            if _skill_present(text, skill):
                matches.append(skill)
        if matches:
            found[category] = sorted(matches, key=str.lower)

    return found


def _skill_present(text: str, skill: str) -> bool:
    """Check a single skill using its compiled boundary-safe pattern."""
    for term, pattern in _TECH_PATTERNS:
        if term.lower() == skill.lower():
            return bool(pattern.search(text))
    return False


def find_alias_skills(text: str) -> List[str]:
    """
    Skills that the resume only mentions through an alias or abbreviation.

    Example: a resume that says ``sklearn`` has the skill "Scikit Learn", but
    the canonical wording is absent. Those hits are reported separately so the
    report can say "recognised through the alias 'sklearn'".

    Returns:
        ``[{'canonical': ..., 'alias': ...}, ...]`` sorted by canonical name.
    """
    if not text:
        return []

    hits: List[Dict] = []
    for alias, pattern in _ALIAS_PATTERNS:
        canonical = all_aliases()[alias]
        # Only report an alias when the canonical wording is NOT present, so a
        # skill is never counted twice.
        if _pattern_for(canonical).search(text):
            continue
        if pattern.search(text):
            hits.append({"canonical": canonical, "alias": alias})

    unique: Dict[str, Dict] = {}
    for hit in hits:
        unique.setdefault(hit["canonical"].lower(), hit)
    return sorted(unique.values(), key=lambda item: item["canonical"].lower())


def find_soft_skills(text: str) -> List[str]:
    """Return soft skills detected in the text, ordered as in the dataset."""
    if not text:
        return []
    detected = [
        skill for skill in soft_skills() if _pattern_for(skill).search(text)
    ]
    return detected


def count_skill_frequency(text: str, skills: List[str]) -> Dict[str, int]:
    """How many times each skill name occurs (keyword density input)."""
    counts: Dict[str, int] = {}
    for skill in skills:
        pattern = _pattern_for(skill)
        found = pattern.findall(text) if text else []
        if found:
            counts[skill] = len(found)
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


# --------------------------------------------------------------------------
# Keyword extraction (TF-IDF, implemented on top of scikit-learn)
# --------------------------------------------------------------------------
def extract_keywords(text: str, top_n: int = 20) -> List[Dict]:
    """
    TF-IDF keyword extraction.

    The resume is treated as a single document. Because TF-IDF normally needs a
    corpus to compare against, we build a small in-memory corpus made of the
    resume itself plus the section texts it contains. Terms that stand out in
    the whole resume *and* inside its sections get the highest score, which
    behaves well for keyword highlighting.
    """
    if not text or len(text.split()) < 20:
        return _frequency_fallback(text, top_n)

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError:  # pragma: no cover - scikit-learn always present in venv
        return _frequency_fallback(text, top_n)

    documents = [text]
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", text) if len(s.strip()) > 40]
    documents.extend(sentences[:80])

    try:
        vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.85,
            max_features=4000,
            token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9+#.\-]{1,}\b",
        )
        matrix = vectorizer.fit_transform(documents)
    except ValueError:
        return _frequency_fallback(text, top_n)

    feature_names = vectorizer.get_feature_names_out()
    # Mean TF-IDF across the corpus emphasises terms repeated in the resume.
    scores = matrix.mean(axis=0).A1
    ranked = sorted(zip(feature_names, scores), key=lambda item: (-item[1], item[0]))

    keywords: List[Dict] = []
    seen_terms: Set[str] = set()
    for term, score in ranked:
        normalised = term.split()[0] if " " in term else term
        if normalised in seen_terms:
            continue
        seen_terms.add(normalised)
        keywords.append(
            {
                "term": term,
                "score": round(float(score), 5),
                "count": count_skill_frequency(text, [term]).get(term, 0)
                or text.lower().count(term),
            }
        )
        if len(keywords) >= top_n:
            break

    return keywords


def _frequency_fallback(text: str, top_n: int) -> List[Dict]:
    """Plain frequency ranking used when there is too little text for TF-IDF."""
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.\-]{1,}", (text or "").lower())
    counter = Counter(token for token in tokens if token not in _COMMON_WORDS and len(token) > 2)
    return [
        {"term": term, "score": round(count / max(len(tokens), 1), 5), "count": count}
        for term, count in counter.most_common(top_n)
    ]


_COMMON_WORDS = {
    "the", "and", "with", "for", "from", "that", "this", "have", "has", "was",
    "were", "will", "are", "our", "their", "which", "using", "used", "use",
    "able", "work", "working", "student", "resume", "email", "phone", "date",
    "including", "also", "such", "into", "over", "other", "than", "they",
}


def frequent_terms(text: str, top_n: int = 15, min_len: int = 3) -> List[Dict]:
    """Most repeated meaningful words (frequency analysis, stop words removed)."""
    tokens = re.findall(r"\b[a-zA-Z][a-zA-Z0-9+#]{%d,}\b" % (min_len - 1), (text or "").lower())
    counter = Counter(token for token in tokens if token not in _COMMON_WORDS)
    total = max(len(tokens), 1)
    return [
        {"term": term, "count": count, "frequency": round(count / total, 4)}
        for term, count in counter.most_common(top_n)
    ]


# --------------------------------------------------------------------------
# Content signals
# --------------------------------------------------------------------------
def find_action_verbs(text: str) -> List[str]:
    """Action verbs used in bullet points (evidence of result-oriented writing)."""
    if not text:
        return []
    words = set(re.findall(r"[a-z]+", text.lower()))
    return sorted((words & ACTION_VERBS))


def count_quantifiers(text: str) -> int:
    """Count measurable results (%, currency, volumes)."""
    return len(QUANTIFIER_RE.findall(text or ""))


def count_filler_phrases(text: str) -> int:
    """Count vague phrases such as 'responsible for' or 'etc.'."""
    if not text:
        return 0
    total = 0
    for phrase in FILLER_WORDS:
        total += len(re.findall(rf"\b{re.escape(phrase)}\b", text, re.I))
    return total


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------
def extract_skills(
    text: str,
    section_text: Dict[str, str] | None = None,
    top_keywords: int = 20,
) -> SkillProfile:
    """
    Build the full :class:`SkillProfile` for a resume.

    Args:
        text: cleaned resume text
        section_text: optional ``{section: body}`` map, used to record which
            section each skill was found in (nice for the report)
    """
    section_text = section_text or {}
    profile = SkillProfile()

    by_category = find_technical_skills(text)
    flat: List[str] = []
    for category, skills in by_category.items():
        for skill in skills:
            flat.append(skill)
            profile.skill_to_category.setdefault(skill, category)

    # Skills mentioned only through an alias ('sklearn' -> 'Scikit Learn').
    profile.aliases_detected = find_alias_skills(text)

    profile.technical_by_category = by_category
    profile.technical = sorted(set(flat), key=str.lower)
    profile.soft = find_soft_skills(text)

    profile.keywords = extract_keywords(text, top_keywords)
    profile.frequent_terms = frequent_terms(text)
    profile.action_verbs = find_action_verbs(text)
    profile.quantifier_count = count_quantifiers(text)
    profile.filler_count = count_filler_phrases(text)
    profile.total_matches = sum(count_skill_frequency(text, profile.technical).values())

    # Where was each technical skill mentioned?
    for skill in profile.technical:
        for section, body in section_text.items():
            if body and _pattern_for(skill).search(body):
                profile.source_sections[skill] = section
                break

    return profile