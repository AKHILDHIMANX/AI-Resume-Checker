"""
AI Resume Checker - backend package.

Holds the analysis modules used by ``app.py``:

* ``resume_parser``  - PDF text extraction + section detection
* ``skill_extractor``- technical / soft skill detection
* ``ats_analyzer``   - ATS compatibility estimation
* ``job_matcher``    - resume-to-role similarity
* ``scoring``        - weighted score aggregation
* ``analyzer``       - orchestrates the full pipeline
"""

__version__ = "1.0.0"