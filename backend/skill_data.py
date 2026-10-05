"""
Skills dataset loader.

The skill vocabulary lives in ``data/skills.json`` so that new skills can be
added without touching any Python code. This module loads the file once,
builds a lookup dictionary of aliases and exposes small helpers used by
``skill_extractor``.

JSON structure
--------------
{
  "categories": {
      "Programming": ["Python", "Java", ...],
      "Web": ["HTML", "CSS", ...],
      ...
  },
  "soft_skills": ["Communication", "Teamwork", ...],
  "skill_aliases": {
      "py": "Python",
      "postgres": "PostgreSQL",
      ...
  }
}

The first term of every category (index 0) acts as the *canonical* name.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Dict, List

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SKILLS_FILE = os.path.join(DATA_DIR, "skills.json")

# Categories whose members are treated as hard / technical skills.
TECHNICAL_CATEGORIES = (
    "Programming",
    "Web",
    "Data",
    "Database",
    "Tools",
    "Cloud / DevOps",
    "Security",
    "Mobile",
    "Operating Systems",
    "Concepts",
)


class SkillDataError(RuntimeError):
    """Raised when ``data/skills.json`` is missing or malformed."""


@lru_cache(maxsize=1)
def load_skill_data() -> Dict:
    """Load and cache the skills JSON file."""
    if not os.path.exists(SKILLS_FILE):
        raise SkillDataError(f"Skills dataset not found at: {SKILLS_FILE}")

    try:
        with open(SKILLS_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:  # pragma: no cover - depends on bad data file
        raise SkillDataError(f"Skills dataset is not valid JSON: {exc}") from exc

    if "categories" not in data or "soft_skills" not in data:
        raise SkillDataError("Skills dataset must contain 'categories' and 'soft_skills'.")

    return data


@lru_cache(maxsize=1)
def technical_skills() -> Dict[str, List[str]]:
    """Return ``{category: [skills...]}`` for technical categories only."""
    data = load_skill_data()
    return {
        name: list(skills)
        for name, skills in data["categories"].items()
        if name in TECHNICAL_CATEGORIES
    }


@lru_cache(maxsize=1)
def soft_skills() -> List[str]:
    """Return the flat list of soft (non technical) skills."""
    return list(load_skill_data()["soft_skills"])


@lru_cache(maxsize=1)
def skill_aliases() -> Dict[str, str]:
    """Return ``{lowercase alias: canonical skill name}`` including names."""
    data = load_skill_data()
    aliases: Dict[str, str] = {}

    for skills in data["categories"].values():
        for skill in skills:
            canonical = skill.strip()
            aliases[canonical.lower()] = canonical
            # "C++" -> also match "c++ programming", handled by regex in extractor
            aliases[canonical.lower().replace(" ", "")] = canonical

    for skill in data["soft_skills"]:
        canonical = skill.strip()
        aliases[canonical.lower()] = canonical

    for alias, canonical in data.get("skill_aliases", {}).items():
        aliases[alias.strip().lower()] = canonical.strip()

    return aliases


def all_aliases() -> Dict[str, str]:
    """Public wrapper around the cached alias map."""
    return skill_aliases()