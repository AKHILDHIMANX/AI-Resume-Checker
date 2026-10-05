"""
Resume parser.

Responsibilities
----------------
1. Extract raw text from an uploaded PDF (pypdf first, pdfplumber as fallback).
2. Clean and normalise that text.
3. Detect standard resume sections with heading patterns.
4. Pull structured details out of each section
   (contact info, education, experience, projects, certifications, ...).

Everything here is deterministic text processing - regular expressions plus
line based heading detection. No external service is used.
"""

from __future__ import annotations

import io
import logging
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

try:  # pragma: no cover - import guard
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None

try:  # pragma: no cover - import guard
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    _pypdf_logger = logging.getLogger("pypdf")
except ImportError:  # pragma: no cover
    PdfReader = None
    _pypdf_logger = None

    class PdfReadError(Exception):
        """Fallback used when pypdf is unavailable."""


# --------------------------------------------------------------------------
# Custom exceptions (handled by the Flask layer for friendly messages)
# --------------------------------------------------------------------------
class ResumeParseError(Exception):
    """Base class for every parser level failure."""


class InvalidPDFError(ResumeParseError):
    """The uploaded file is not a readable PDF."""


class EmptyPDFError(ResumeParseError):
    """The PDF contains no extractable text (scanned image, empty file...)."""


# --------------------------------------------------------------------------
# Section definitions
# --------------------------------------------------------------------------
# Each canonical section maps to the heading spellings we accept. The order of
# SECTION_ORDER is also used as a tie-break when two headings appear on the
# same line.
SECTION_ALIASES: Dict[str, List[str]] = {
    "summary": [
        "professional summary", "career summary", "executive summary",
        "professional profile", "career objective", "objective",
        "profile", "summary", "about me", "about", "personal details",
    ],
    "education": [
        "education", "academic background", "academic qualifications",
        "educational qualification", "educational qualifications",
        "qualification", "qualifications", "academics",
        "educational background", "education & training", "education and training",
    ],
    "skills": [
        "skills", "skill set", "skill summary", "technical skills",
        "key skills", "core competencies", "competencies", "areas of expertise",
        "techno skills", "it skills", "computer skills",
    ],
    "experience": [
        "work experience", "professional experience", "employment history",
        "experience", "internship", "internships", "work history",
        "employment", "industrial training", "training", "appointments",
    ],
    "projects": [
        "projects", "academic projects", "personal projects",
        "major projects", "project work", "key projects", "portfolio",
    ],
    "certifications": [
        "certifications", "certification", "licenses", "licences",
        "courses", "online courses", "certificates", "training certificates",
    ],
    "achievements": [
        "achievements", "accomplishments", "awards", "honors", "honours",
        "achievements & awards", "awards and achievements", "key achievements",
        "extra curricular activities", "extracurricular activities",
    ],
    "languages": ["languages", "language proficiency", "known languages"],
    "interests": ["interests", "hobbies", "areas of interest", "interest"],
    "references": ["references", "referees"],
}

SECTION_ORDER: List[str] = list(SECTION_ALIASES.keys())

# Human friendly labels used in the report / missing-section list.
SECTION_LABELS: Dict[str, str] = {
    "summary": "Summary / Objective",
    "education": "Education",
    "skills": "Skills",
    "experience": "Experience",
    "projects": "Projects",
    "certifications": "Certifications",
    "achievements": "Achievements / Awards",
    "languages": "Languages",
    "interests": "Interests / Hobbies",
    "references": "References",
}

# Sections that a fresher / student resume is expected to contain.
RECOMMENDED_SECTIONS: List[str] = [
    "summary", "education", "skills", "experience", "projects",
]

OPTIONAL_SECTIONS: List[str] = [
    "certifications", "achievements", "languages", "interests", "references",
]

# Headings are usually short lines written in capitals or ending with ':'.
# The regex keeps common separators so "TECHNICAL SKILLS:" also matches.
_HEADING_NOISE = re.compile(r"[^a-z/&+ ]")


# --------------------------------------------------------------------------
# Data containers
# --------------------------------------------------------------------------
@dataclass
class ContactInfo:
    """Contact block extracted from the top of the resume."""

    name: Optional[str] = None
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "emails": self.emails,
            "phones": self.phones,
            "links": self.links,
            "locations": self.locations,
        }

    @property
    def completeness(self) -> int:
        """0-100: how much of the basic contact block is present."""
        checks = [bool(self.name), bool(self.emails), bool(self.phones), bool(self.links)]
        return round(100 * sum(checks) / len(checks))


@dataclass
class EducationEntry:
    degree: Optional[str] = None
    institution: Optional[str] = None
    year: Optional[str] = None
    score: Optional[str] = None
    raw: str = ""

    def to_dict(self) -> Dict:
        return {
            "degree": self.degree,
            "institution": self.institution,
            "year": self.year,
            "score": self.score,
            "raw": self.raw,
        }


@dataclass
class ExperienceEntry:
    title: Optional[str] = None
    organisation: Optional[str] = None
    duration: Optional[str] = None
    raw: str = ""

    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "organisation": self.organisation,
            "duration": self.duration,
            "raw": self.raw,
        }


@dataclass
class ProjectEntry:
    name: Optional[str] = None
    tech: Optional[str] = None
    raw: str = ""

    def to_dict(self) -> Dict:
        return {"name": self.name, "tech": self.tech, "raw": self.raw}


@dataclass
class CertificationEntry:
    name: Optional[str] = None
    issuer: Optional[str] = None
    year: Optional[str] = None
    raw: str = ""

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "issuer": self.issuer,
            "year": self.year,
            "raw": self.raw,
        }


@dataclass
class ParsedResume:
    """Everything the parser could learn about a resume."""

    raw_text: str = ""
    clean_text: str = ""
    pages: int = 0
    word_count: int = 0
    char_count: int = 0
    contact: ContactInfo = field(default_factory=ContactInfo)
    sections_found: List[str] = field(default_factory=list)
    sections_missing: List[str] = field(default_factory=list)
    section_text: Dict[str, str] = field(default_factory=dict)
    education: List[EducationEntry] = field(default_factory=list)
    experience: List[ExperienceEntry] = field(default_factory=list)
    projects: List[ProjectEntry] = field(default_factory=list)
    certifications: List[CertificationEntry] = field(default_factory=list)
    achievements: List[str] = field(default_factory=list)
    languages_listed: List[str] = field(default_factory=list)
    interests: List[str] = field(default_factory=list)
    summary_text: str = ""
    metrics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "raw_text": self.raw_text,
            "pages": self.pages,
            "word_count": self.word_count,
            "char_count": self.char_count,
            "contact": self.contact.to_dict(),
            "contact_completeness": self.contact.completeness,
            "sections_found": self.sections_found,
            "sections_missing": self.sections_missing,
            "section_text": self.section_text,
            "education": [item.to_dict() for item in self.education],
            "experience": [item.to_dict() for item in self.experience],
            "projects": [item.to_dict() for item in self.projects],
            "certifications": [item.to_dict() for item in self.certifications],
            "achievements": self.achievements,
            "languages": self.languages_listed,
            "interests": self.interests,
            "summary_text": self.summary_text,
            "metrics": self.metrics,
        }


# --------------------------------------------------------------------------
# 1. PDF text extraction
# --------------------------------------------------------------------------
def _looks_like_pdf(data: bytes) -> bool:
    """A PDF always starts with the %PDF- magic bytes."""
    return data[:5] == b"%PDF-" or data[:1024].find(b"%PDF-") != -1


@contextmanager
def _quiet_pypdf() -> Iterator[None]:
    """
    Silence pypdf's internal warnings for the duration of the block.

    pypdf writes things like ``EOF marker not found`` to the log when it meets
    a damaged file. Those files are already turned into a clear, user facing
    error message by the exception handling around the reader, so the extra
    console noise would only confuse the developer running the app. The
    previous level is always restored, and the logger's own handlers are left
    untouched.
    """
    if _pypdf_logger is None:  # pragma: no cover - pypdf missing
        yield
        return

    previous = _pypdf_logger.level
    _pypdf_logger.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        _pypdf_logger.setLevel(previous)


def extract_text_from_pdf(file_bytes: bytes) -> Tuple[str, int]:
    """
    Extract text from raw PDF bytes.

    Strategy: ``pypdf`` for speed, ``pdfplumber`` as a fallback for PDFs whose
    text layer pypdf cannot read.

    Returns:
        (extracted_text, page_count)

    Raises:
        InvalidPDFError  - not a PDF / corrupted / password protected
        EmptyPDFError    - valid PDF but no text layer
    """
    if not file_bytes:
        raise EmptyPDFError("The uploaded file is empty (0 bytes).")

    if not _looks_like_pdf(file_bytes):
        raise InvalidPDFError("The uploaded file is not a valid PDF document.")

    if PdfReader is None:  # pragma: no cover
        raise InvalidPDFError("PDF support is unavailable: pypdf is not installed.")

    stream = io.BytesIO(file_bytes)
    text_parts: List[str] = []
    page_count = 0

    try:
        with _quiet_pypdf():
            reader = PdfReader(stream)
            if getattr(reader, "is_encrypted", False):
                try:
                    reader.decrypt("")
                except Exception as exc:  # noqa: BLE001
                    raise InvalidPDFError(
                        "The PDF is password protected and cannot be read."
                    ) from exc

            page_count = len(reader.pages)
            if page_count == 0:
                raise EmptyPDFError("The PDF does not contain any pages.")

            for page in reader.pages:
                try:
                    text_parts.append(page.extract_text() or "")
                except Exception:  # noqa: BLE001 - a broken page must not kill the run
                    text_parts.append("")
    except (InvalidPDFError, EmptyPDFError):
        raise
    except PdfReadError as exc:
        raise InvalidPDFError(
            "The PDF appears to be corrupted or damaged and could not be opened."
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise InvalidPDFError(
            "The PDF could not be read. It may be corrupted or not a real PDF."
        ) from exc

    text = "\n".join(text_parts).strip()

    # Fallback: pdfplumber often recovers text that pypdf misses.
    if len(re.sub(r"\s", "", text)) < 120 and pdfplumber is not None:
        recovered = ""
        try:
            with _quiet_pypdf():
                recovered = _extract_with_pdfplumber(file_bytes)
        except Exception:  # noqa: BLE001
            recovered = ""
        if len(recovered.strip()) > len(text):
            text = recovered.strip()
            if page_count == 0:
                page_count = _count_pages_pdfplumber(file_bytes)

    if not text.strip():
        raise EmptyPDFError(
            "No selectable text was found in this PDF. It is most likely a "
            "scanned image - please upload a text-based (digital) PDF."
        )

    if len(re.sub(r"\s", "", text)) < 40:
        raise EmptyPDFError(
            "Only a very small amount of text could be extracted from this PDF, "
            "so it cannot be analysed reliably."
        )

    return text, page_count


def _extract_with_pdfplumber(file_bytes: bytes) -> str:
    """Best-effort second extraction pass using pdfplumber."""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception:  # noqa: BLE001
        return ""


def _count_pages_pdfplumber(file_bytes: bytes) -> int:
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            return len(pdf.pages)
    except Exception:  # noqa: BLE001
        return 0


# --------------------------------------------------------------------------
# 2. Text cleaning
# --------------------------------------------------------------------------
_LIGATURES = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
}
_BULLETS = "\u2022\u25aa\u25cf\u25cb\u2043\u2219\u00b7\u2023\u2024\u25a0\u29be\u2b58\ufe0f"


def clean_text(text: str) -> str:
    """
    Normalise extracted text.

    * expand ligatures and smart punctuation (PDFs love ligatures)
    * normalise bullets to a single '-'
    * unify unicode quotes / dashes
    * collapse 3+ blank lines and trailing spaces
    """
    if not text:
        return ""

    for src, dst in _LIGATURES.items():
        text = text.replace(src, dst)

    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    text = text.replace("\u00a0", " ").replace("\u200b", "").replace("\ufeff", "")
    text = text.replace("\t", " ")

    # Any bullet-ish character becomes "- " so line parsing stays simple.
    for bullet in _BULLETS:
        text = text.replace(bullet, "-")

    # De-hyphenate words split across lines ("develop-\nment").
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    lines = [re.sub(r"[ ]{2,}", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def preprocess(text: str) -> List[str]:
    """
    Tokenise + normalise text for the NLP steps.

    Returns lowercase word tokens (stop words removed) - used for TF-IDF,
    frequency analysis and cosine similarity.
    """
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.\-]*", text.lower())
    return [token for token in tokens if token not in STOP_WORDS and len(token) > 1]


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "for", "from",
    "has", "have", "he", "her", "his", "i", "in", "is", "it", "its", "me", "my",
    "of", "on", "or", "our", "she", "so", "that", "the", "their", "them", "they",
    "this", "to", "was", "were", "what", "when", "which", "who", "will", "with",
    "you", "your", "am", "any", "can", "do", "does", "doing", "done", "each",
    "etc", "if", "into", "just", "more", "most", "no", "not", "now", "only",
    "other", "over", "own", "same", "should", "some", "such", "than", "then",
    "there", "these", "they", "those", "through", "under", "up", "very", "was",
    "were", "while", "will", "with", "would", "you", "able", "across", "also",
    "among", "because", "been", "being", "between", "both", "during", "either",
    "however", "including", "indeed", "instead", "least", "like", "made", "make",
    "many", "may", "might", "must", "need", "often", "per", "please", "since",
    "still", "upon", "us", "use", "used", "using", "via", "well", "whether",
}


# --------------------------------------------------------------------------
# 3. Section detection
# --------------------------------------------------------------------------
def _normalise_heading(line: str) -> str:
    line = line.strip().strip(":-–—•*_ \t")
    line = _HEADING_NOISE.sub(" ", line.lower())
    return re.sub(r"\s+", " ", line).strip()


def _alias_lookup() -> Dict[str, str]:
    """Map every accepted heading spelling to its canonical section key."""
    lookup: Dict[str, str] = {}
    for canonical, aliases in SECTION_ALIASES.items():
        lookup[_normalise_heading(canonical)] = canonical
        for alias in aliases:
            lookup[_normalise_heading(alias)] = canonical
    # A few very common variants.
    lookup[_normalise_heading("work experience & projects")] = "experience"
    lookup[_normalise_heading("skills & tools")] = "skills"
    lookup[_normalise_heading("technical skills & tools")] = "skills"
    lookup[_normalise_heading("education & experience")] = "education"
    return lookup


HEADING_LOOKUP = _alias_lookup()

# Words that only join section names, e.g. "ACHIEVEMENTS AND PROJECTS".
_HEADING_JOINERS = {"and", "or", "of", "the", "a", "an"}

# Every word that can appear inside a recognised section heading.
_SECTION_WORDS = {
    word
    for heading in HEADING_LOOKUP
    for word in heading.split()
    if word not in _HEADING_JOINERS
}


def detect_sections(text: str) -> Tuple[List[str], Dict[str, str]]:
    """
    Split the resume into sections.

    A line is treated as a heading when it is short (<= 60 characters), has no
    sentence-ending punctuation, and its normalised form matches a known
    heading (or is a heading in capitals with <= 4 words).

    Returns:
        (ordered list of detected section keys, {section: section body})
    """
    if not text:
        return [], {}

    lines = text.splitlines()
    # Pre-tokenised positions of every recognised heading.
    heading_positions: List[Tuple[int, str]] = []
    seen: set = set()

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) > 60:
            continue
        if stripped.endswith((".", "!", "?", ",", ";")) and not stripped.endswith(":"):
            # Sentence, not a heading.
            if len(stripped.split()) > 6:
                continue

        normalised = _normalise_heading(stripped)
        if not normalised:
            continue

        canonical = HEADING_LOOKUP.get(normalised)

        if canonical is None:
            # Fallback: ALL-CAPS short line such as "TECHNICAL SKILLS".
            words = stripped.split()
            letters = [c for c in stripped if c.isalpha()]
            is_caps = bool(letters) and all(
                c.isupper() for c in letters
            ) and 1 <= len(words) <= 4
            if is_caps:
                canonical = HEADING_LOOKUP.get(normalised)
                if canonical is None:
                    # Try matching by containment, e.g. "PROFESSIONAL EXPERIENCE".
                    for alias_norm, key in HEADING_LOOKUP.items():
                        if len(alias_norm) >= 6 and alias_norm in normalised:
                            canonical = key
                            break
        if canonical is None:
            continue

        if canonical in seen:
            continue
        seen.add(canonical)
        heading_positions.append((index, canonical))

    heading_positions.sort(key=lambda item: item[0])

    section_text: Dict[str, str] = {}
    for position, (line_index, canonical) in enumerate(heading_positions):
        end = (
            heading_positions[position + 1][0]
            if position + 1 < len(heading_positions)
            else len(lines)
        )
        body = "\n".join(lines[line_index + 1 : end]).strip()
        # If two headings were merged, keep the richer body.
        if canonical not in section_text or len(body) > len(section_text[canonical]):
            section_text[canonical] = body

    detected = [canonical for _, canonical in heading_positions]
    return detected, section_text


# --------------------------------------------------------------------------
# 4. Field level extraction
# --------------------------------------------------------------------------
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
# Deliberately permissive: 7-15 digits with optional +, spaces, dashes, dots.
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s.\-]?)?(?:\(\d{2,4}\)[\s.\-]?)?\d{3,5}[\s.\-]?\d{3,5}"
    r"(?:[\s.\-]?\d{2,4})?"
)
URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}(?:/[^\s,;]*)?"
)
# Only treat a URL as a profile link when it looks like a real web address.
LINK_RE = re.compile(
    r"(?:https?://|www\.)\S+"
    r"|(?:linkedin|github|gitlab|bitbucket|behance|dribbble|stackoverflow|medium|"
    r"portfolio|dev|me|tech)\.[a-z]{2,4}/[^\s,;]*"
    r"|[a-z0-9][a-z0-9.\-]*\.(?:com|net|org|io|dev|in|co|me|edu)(?:/[^\s,;]*)?",
    re.I,
)
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/[^\s,;]+", re.I)
GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[^\s,;]+", re.I)
LOCATION_RE = re.compile(
    r"\b(?:based in|address|location)\s*[:\-]\s*([A-Za-z .,'-]{3,40})", re.I
)

# Degree markers, longest first so "higher secondary" wins over "secondary".
DEGREE_WORDS = (
    "higher secondary", "bachelor of technology", "master of technology",
    "bachelor of computer applications", "master of computer applications",
    "bachelor of business administration", "master of business administration",
    "bachelor of science", "master of science", "bachelor of arts",
    "master of arts", "bachelor of engineering", "master of engineering",
    "doctor of philosophy", "post graduate diploma", "diploma in",
    "b.tech", "btech", "btech.", "b.e", "b.sc", "bsc", "b.com", "bca",
    "m.tech", "mtech", "m.e", "msc", "mca", "mba", "b.a", "b.s", "bs",
    "ph.d", "phd", "m.phil", "master", "bachelor", "diploma", "12th",
    "10th", "intermediate", "secondary",
)
INSTITUTION_WORDS = (
    "university", "college", "institute", "institution", "school", "academy",
    "polytechnic", "deemed", "campus",
)
_DEGREE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:" + "|".join(re.escape(w) for w in DEGREE_WORDS) + r")(?![A-Za-z0-9])",
    re.I,
)
_INSTITUTION_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:" + "|".join(INSTITUTION_WORDS) + r")(?![A-Za-z0-9])", re.I
)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
PERCENT_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,2})?\s?%")
CGPA_RE = re.compile(r"\b(?:cgpa|cpa|gpa)\s*[:\-]?\s*(\d{1,2}(?:\.\d{1,2})?)\s*/?\s*(\d{1,2}(?:\.\d{1,2})?)?", re.I)
DATE_RANGE_RE = re.compile(
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*'?\d{2,4}"
    r"|\d{1,2}[/\-.]\d{2,4}|\d{4})\s*(?:-|–|to|—)\s*"
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*'?\d{2,4}"
    r"|\d{1,2}[/\-.]\d{2,4}|\d{4}|present|current|ongoing|now)",
    re.I,
)
BULLET_RE = re.compile(r"^\s*[-•*+]\s+|\s\d+[.)]\s")
# Separators used to split a single line into fields. "/" is deliberately
# excluded so that "PL/SQL", "CI/CD" and "Node.js" survive intact.
SEPARATOR_RE = re.compile(r"\s*(?:[|•·–—]+\s*)\s*|\s+\|\s+")


def _clean_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip(" \t|,-–—•·/\\")
    value = re.sub(r"\s{2,}", " ", value)
    return value or None


def extract_contact(text: str) -> ContactInfo:
    """Pull name / email / phone / links out of the header block."""
    contact = ContactInfo()
    if not text:
        return contact

    head = "\n".join(text.splitlines()[:14])

    contact.emails = sorted(set(EMAIL_RE.findall(text)))

    # Profile links live in the header block. Anything that is part of an
    # email address, or a file name, is discarded.
    header = "\n".join(text.splitlines()[:10])
    candidates: List[str] = []
    for found in LINK_RE.findall(header):
        candidate = found.strip().rstrip(".,;)")
        if not candidate:
            continue
        if any(candidate in email for email in contact.emails):
            continue
        if re.search(r"\.(?:png|jpe?g|gif|pdf|docx?)$", candidate, re.I):
            continue
        candidates.append(candidate)
    if not candidates:
        candidates = [m.strip() for m in LINKEDIN_RE.findall(text)] + [
            m.strip() for m in GITHUB_RE.findall(text)
        ]
    contact.links = sorted(set(candidates))

    phones = []
    for candidate in PHONE_RE.findall(head):
        digits = re.sub(r"\D", "", candidate)
        if not 9 <= len(digits) <= 15:
            continue
        # Skip year-like / date-like noise.
        if YEAR_RE.fullmatch(candidate.strip()):
            continue
        phones.append(candidate.strip())
    # de-duplicate while preserving order
    contact.phones = list(dict.fromkeys(phones))

    for match in LOCATION_RE.finditer(text):
        value = _clean_value(match.group(1))
        if value and value.lower() not in {"india", "india."}:
            contact.locations.append(value)

    contact.name = _guess_name(text, contact)
    return contact


def _guess_name(text: str, contact: ContactInfo) -> Optional[str]:
    """
    A resume name is normally the first meaningful line of the document and is
    not a heading / contact line.
    """
    stop_words = {
        "resume", "curriculum vitae", "cv", "profile", "objective", "summary",
        "contact", "details", "personal", "information",
    }
    for line in text.splitlines()[:10]:
        stripped = line.strip(" \t|,:;–—-•*")
        if not stripped or len(stripped) < 3 or len(stripped) > 55:
            continue
        if stripped.lower() in stop_words or "curriculum" in stripped.lower():
            continue
        if HEADING_LOOKUP.get(_normalise_heading(stripped)):
            continue
        if EMAIL_RE.search(stripped) or PHONE_RE.search(stripped):
            continue
        if URL_RE.search(stripped):
            continue
        words = stripped.split()
        if not 1 < len(words) <= 5:
            continue
        # Names look like capitalised words and contain no digits.
        if any(char.isdigit() for char in stripped):
            continue
        if not re.match(r"^[A-Za-z][A-Za-z.'\- ]*$", stripped):
            continue
        capitalised = sum(
            1 for word in words if word[:1].isupper() or word.lower() in {"van", "de", "of"}
        )
        if capitalised / len(words) >= 0.6:
            return stripped.title() if stripped.islower() else stripped
    return None


def _content_lines(block: str) -> List[str]:
    """Split a section body into meaningful lines, dropping blanks."""
    if not block:
        return []
    return [
        line.strip()
        for line in block.splitlines()
        if line.strip() and not line.strip().lower() in {"-", "*", ""}
    ]


def extract_education(section_body: str) -> List[EducationEntry]:
    """Parse education entries (degree, institution, year, CGPA/percentage)."""
    entries: List[EducationEntry] = []
    lines = _content_lines(section_body)
    if not lines:
        return entries

    # Group lines: a new entry starts at a line with a degree / institution word.
    groups: List[List[str]] = []
    current: List[str] = []
    for line in lines:
        starts_entry = bool(_DEGREE_RE.search(line) or _INSTITUTION_RE.search(line))
        if starts_entry and current:
            groups.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        groups.append(current)

    for group in groups:
        joined = " ".join(group)

        degree_match = _DEGREE_RE.search(joined)
        institution_match = _INSTITUTION_RE.search(joined)

        # Degree = text from the degree marker up to the institution marker,
        # the first year, or the end of the line - whichever comes first.
        degree = None
        if degree_match:
            start = degree_match.start()
            stops = [len(joined)]
            if institution_match and institution_match.start() > start:
                # Prefer the comma that separates degree from institution.
                prefix = joined[start : institution_match.start()]
                comma = prefix.rfind(",")
                if comma > 0:
                    stops.append(start + comma)
                else:
                    stops.append(institution_match.start())
            year_hits = [m.start() for m in YEAR_RE.finditer(joined) if m.start() > start]
            stops.extend(year_hits)
            end = min(stops)
            degree = _clean_value(joined[start:end].strip(" ,-–—|"))

        institution = None
        if institution_match:
            keyword_end = institution_match.end()
            # The institution name usually starts at the previous comma.
            comma = joined.rfind(",", 0, institution_match.start())
            if comma > (degree_match.end() if degree_match else 0):
                head = joined[comma + 1 : keyword_end]
            else:
                head = joined[
                    (degree_match.end() if degree_match else 0) : keyword_end
                ]
            words = [w for w in head.strip(" ,-–—|").split() if w]
            institution = _clean_value(" ".join(words[-5:])) if words else None

        years = [match.group(0) for match in YEAR_RE.finditer(joined)]
        year = min(years) if years else None

        score = None
        percent = PERCENT_RE.search(joined)
        cgpa = CGPA_RE.search(joined)
        if cgpa:
            score = _clean_value(cgpa.group(0))
        elif percent:
            score = percent.group(0)

        entries.append(
            EducationEntry(
                degree=degree,
                institution=institution,
                year=year,
                score=score,
                raw=_clean_value(joined) or joined,
            )
        )

    return entries


ROLE_HINTS = (
    "developer", "engineer", "intern", "analyst", "scientist", "manager",
    "assistant", "consultant", "administrator", "executive", "officer",
    "designer", "administrator", "fresher", "trainee", "associate",
    "scientist", "researcher", "teacher", "lecturer", "executive",
)


def extract_experience(section_body: str) -> List[ExperienceEntry]:
    """
    Parse experience entries. Experience resumes rarely follow a strict schema,
    so entries are grouped by the lines that carry a date range.
    """
    entries: List[ExperienceEntry] = []
    lines = _content_lines(section_body)
    if not lines:
        return entries

    current: List[str] = []
    groups: List[List[str]] = []

    for line in lines:
        has_range = bool(DATE_RANGE_RE.search(line))
        has_bullet = bool(BULLET_RE.match(line)) or line.startswith("-")
        if (has_range and current) or (has_range and not current):
            if current:
                groups.append(current)
            current = [line]
        else:
            if not current and (has_bullet and not has_range):
                current = [line]
            else:
                current.append(line)
    if current:
        groups.append(current)

    for group in groups:
        joined = " ".join(group)
        header = group[0]
        date_match = DATE_RANGE_RE.search(header)
        duration = None
        if date_match:
            duration = f"{date_match.group(1).strip()} - {date_match.group(2).strip()}"

        # Strip the date range, then split the remaining header on commas.
        header_clean = BULLET_RE.sub("", header)
        if date_match:
            header_clean = header_clean[: date_match.start()] + header_clean[date_match.end():]
        parts = [p.strip() for p in header_clean.split(",") if p.strip()]

        title = _clean_value(parts[0]) if parts else _clean_value(header)
        organisation = _clean_value(parts[1]) if len(parts) > 1 else None

        if title and len(title.split()) > 12:
            title = _clean_value(header)

        if organisation is None:
            for line in group[:3]:
                low = line.lower()
                if any(hint in low for hint in ROLE_HINTS) and line != header:
                    organisation = _clean_value(line)
                    break

        entries.append(
            ExperienceEntry(
                title=title,
                organisation=organisation,
                duration=duration,
                raw=_clean_value(joined) or joined,
            )
        )

    return entries


def extract_projects(section_body: str) -> List[ProjectEntry]:
    """Parse project entries: name plus an optional tech stack note."""
    entries: List[ProjectEntry] = []
    lines = _content_lines(section_body)
    if not lines:
        return entries

    current: List[str] = []
    groups: List[List[str]] = []

    for line in lines:
        starts = line.startswith("-") or bool(re.match(r"^\s*\d+[.)]", line))
        if starts:
            if current:
                groups.append(current)
            current = [line.lstrip("-*• \t")]
        elif current:
            current.append(line)
        else:
            current = [line]
    if current:
        groups.append(current)

    for group in groups:
        joined = " ".join(group)
        # A project line is usually "Name - description (tech)".
        parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", joined) if p.strip()]
        if not parts:
            parts = [p for p in SEPARATOR_RE.split(joined) if p.strip()]
        name = _clean_value(parts[0]) if parts else _clean_value(joined)
        if name and len(name) > 70:
            # Keep the leading clause only - the rest is description.
            head = name[:70].rsplit(",", 1)[0]
            name = _clean_value(head or name[:70])
        tech = None
        tech_match = re.search(
            r"(?:using|with|tech(?:nolog)?(?:y|ies)?|built (?:with|on)|tools?)\s*[:\-]?\s*(.+)$",
            joined,
            re.I,
        )
        if tech_match:
            tech = _clean_value(tech_match.group(1))
        elif len(parts) > 1 and len(parts[1]) <= 80:
            tech = _clean_value(parts[1])

        entries.append(ProjectEntry(name=name, tech=tech, raw=_clean_value(joined) or joined))

    return entries


def extract_certifications(section_body: str) -> List[CertificationEntry]:
    """Parse certification lines into (name, issuer, year) when detectable."""
    entries: List[CertificationEntry] = []
    lines = _content_lines(section_body)
    for line in lines:
        cleaned = BULLET_RE.sub("", line).strip()
        if not cleaned:
            continue
        parts = [
            p.strip()
            for p in re.split(r",|\s+[-–—]\s+|\s*\|\s*", cleaned)
            if p.strip()
        ]
        name = _clean_value(parts[0]) if parts else _clean_value(cleaned)
        issuer = _clean_value(parts[1]) if len(parts) > 1 else None
        year_match = YEAR_RE.search(cleaned)
        year = year_match.group(0) if year_match else None
        if year and issuer and year in issuer:
            issuer = _clean_value(issuer.replace(year, ""))
        entries.append(
            CertificationEntry(
                name=name,
                issuer=issuer,
                year=year,
                raw=_clean_value(cleaned) or cleaned,
            )
        )
    return entries


def _is_heading_line(line: str) -> bool:
    """
    True when a content line is really another section heading.

    Resumes often combine sections ("ACHIEVEMENTS AND PROJECTS") or place a
    heading at the end of the previous block, so a raw line-by-line read can
    return "ACHIEVEMENTS AND PROJECTS" as if it were an achievement. A line is
    treated as a heading when it is a known alias, or when every meaningful
    word in it is a section word (after removing joiners).
    """
    stripped = line.strip()
    if not stripped:
        return False

    normalised = _normalise_heading(stripped)
    if not normalised or normalised in HEADING_LOOKUP:
        return bool(normalised)

    words = [w for w in normalised.split() if w not in _HEADING_JOINERS]
    if words and all(word in _SECTION_WORDS for word in words):
        return True

    # An all-caps line with no sentence punctuation is almost always a heading.
    letters = [c for c in stripped if c.isalpha()]
    return (
        len(words) <= 6
        and letters
        and all(c.isupper() for c in letters)
        and not stripped.endswith((".", ",", ";"))
    )


def extract_bullet_items(section_body: str, limit: int = 12) -> List[str]:
    """Return cleaned bullet lines (achievements, interests, languages...)."""
    items: List[str] = []
    for line in _content_lines(section_body):
        if _is_heading_line(line):
            continue
        cleaned = _clean_value(BULLET_RE.sub("", line))
        if cleaned and len(cleaned) > 2:
            items.append(cleaned)
        if len(items) >= limit:
            break
    return items


def _language_from_item(item: str) -> Optional[str]:
    """Pull 'English - Fluent (B2)' down to 'English'."""
    cleaned = SEPARATOR_RE.split(item)[0].strip()
    cleaned = re.sub(
        r"\s*\((?:native|fluent|advanced|intermediate|basic|beginner).*\)\s*$", "", cleaned, flags=re.I
    )
    cleaned = re.sub(
        r"\s*[-–]?\s*(?:native|fluent|advanced|intermediate|basic|beginner|proficient).*$",
        "",
        cleaned,
        flags=re.I,
    ).strip()
    return _clean_value(cleaned) if cleaned and len(cleaned) <= 30 else None


# --------------------------------------------------------------------------
# 5. Readability / formatting metrics
# --------------------------------------------------------------------------
def compute_metrics(text: str, pages: int) -> Dict[str, float]:
    """Simple, explainable formatting statistics used by the ATS analyzer."""
    lines = [line for line in text.splitlines()]
    non_empty = [line for line in lines if line.strip()]
    words = re.findall(r"[A-Za-z][A-Za-z0-9'\-]*", text)
    sentences = re.findall(r"[.!?]+", text)

    special_chars = len(re.findall(r"[^\w\s.,;:()\[\]@#%&+\-/']", text))
    bullets = len([line for line in non_empty if BULLET_RE.match(line)])
    headings_upper = len(
        [
            line
            for line in non_empty
            if len(line.split()) <= 4
            and line.isupper()
            and any(c.isalpha() for c in line)
        ]
    )
    long_lines = len([line for line in non_empty if len(line) > 110])

    avg_sentence_len = (len(words) / len(sentences)) if sentences else 0.0

    return {
        "word_count": float(len(words)),
        "line_count": float(len(lines)),
        "non_empty_lines": float(len(non_empty)),
        "pages": float(pages or 1),
        "special_char_count": float(special_chars),
        "special_char_ratio": round(special_chars / max(len(text), 1) * 1000, 3),
        "bullet_count": float(bullets),
        "avg_line_length": round(
            sum(len(line) for line in non_empty) / max(len(non_empty), 1), 2
        ),
        "avg_sentence_length": round(avg_sentence_len, 2),
        "uppercase_headings": float(headings_upper),
        "long_lines": float(long_lines),
        "digit_ratio": round(len(re.findall(r"\d", text)) / max(len(text), 1) * 1000, 3),
    }


# --------------------------------------------------------------------------
# 6. Top level parse function
# --------------------------------------------------------------------------
def parse_resume(file_bytes: bytes) -> ParsedResume:
    """
    Full parse pipeline: extract -> clean -> detect sections -> pull fields.

    Raises ResumeParseError subclasses for invalid / unusable uploads.
    """
    raw_text, pages = extract_text_from_pdf(file_bytes)
    clean = clean_text(raw_text)

    resume = ParsedResume(raw_text=raw_text, clean_text=clean, pages=pages)
    resume.word_count = len(clean.split())
    resume.char_count = len(clean)
    resume.metrics = compute_metrics(clean, pages)

    resume.contact = extract_contact(clean)
    detected, section_text = detect_sections(clean)
    resume.sections_found = detected
    resume.section_text = section_text

    resume.sections_missing = [
        key
        for key in RECOMMENDED_SECTIONS + OPTIONAL_SECTIONS
        if key not in detected
    ]

    resume.summary_text = _clean_value(section_text.get("summary", "").replace("\n", " ")) or ""
    resume.education = extract_education(section_text.get("education", ""))
    resume.experience = extract_experience(section_text.get("experience", ""))
    resume.projects = extract_projects(section_text.get("projects", ""))
    resume.certifications = extract_certifications(section_text.get("certifications", ""))

    resume.achievements = extract_bullet_items(section_text.get("achievements", ""))

    language_items = extract_bullet_items(section_text.get("languages", ""))
    resume.languages_listed = [
        lang
        for lang in (_language_from_item(item) for item in language_items)
        if lang
    ]

    resume.interests = [
        SEPARATOR_RE.split(item)[0].strip()
        for item in extract_bullet_items(section_text.get("interests", ""))
    ]
    resume.interests = [i for i in resume.interests if i]

    return resume