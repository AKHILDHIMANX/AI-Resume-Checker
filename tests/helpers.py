"""
Shared helpers for the AI Resume Checker test-suite.

The tests must not depend on any real personal resume, so a small synthetic
PDF is generated at runtime with matplotlib's PDF backend. The document is
built in memory and never written to the repository.
"""

from __future__ import annotations

import io
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# --------------------------------------------------------------------------
# Sample resume text (purely fictional, no personal data)
# --------------------------------------------------------------------------
SAMPLE_RESUME = """John Doe
john.doe@example.com | +91 98765 43210 | Chandigarh, India
linkedin.com/in/johndoe | github.com/johndoe

PROFESSIONAL SUMMARY
Final year MCA student with hands-on experience in Python and Java application
development. Built academic projects using Flask, MySQL and REST APIs. Strong
communication and teamwork skills developed through college technical events.

EDUCATION
Bachelor of Computer Applications (BCA), Chandigarh University, 2024
CGPA: 8.4/10

TECHNICAL SKILLS
Programming: Python, Java, C, SQL, JavaScript
Web: HTML, CSS, Flask, Django, React, Node.js, REST API
Data: Pandas, NumPy, Matplotlib, Machine Learning
Database: MySQL, PostgreSQL, MongoDB, Oracle
Tools: Git, GitHub, Docker, VS Code, Linux

PROJECTS
- AI Resume Checker Web Application using Flask and SQLite - built a keyword matching
  engine with TF-IDF and cosine similarity for a 3 member team
- Student Attendance System in Python and MySQL, reduced manual register
  entry time by 60 percent

WORK EXPERIENCE
Software Developer Intern, Tech Solutions Pvt Ltd - June 2024 to December 2024
- Developed REST API endpoints in Flask for a college management system
- Wrote 40 SQL queries to generate automated attendance and grade reports
- Improved page load time by 35 percent by adding pagination and caching

CERTIFICATIONS
- Oracle PL/SQL Programming, Oracle University, 2023
- Python for Data Science, Coursera, 2024

ACHIEVEMENTS
- First prize in Inter-College Hackathon, 2024
- Dean's List for academic excellence

LANGUAGES
English - Fluent
Hindi - Native

INTERESTS
Web Development, Open Source, Chess
"""

MINIMAL_RESUME = """Anita Sharma
anita.sharma@example.com | +91 90000 12345

Skills
Python, SQL, Pandas

Projects
- Library management system in Python
"""

NO_SKILLS_RESUME = """Ravi Kumar
+91 91111 22233
An engineer with an engineering degree from a university in 2019 who worked
for a company in 2020 and 2021 and 2022 and is now looking for a position.
He was responsible for various tasks and helped the team with daily work and
other duties assigned to him during his tenure at that organisation.
"""


# --------------------------------------------------------------------------
# PDF builders
# --------------------------------------------------------------------------
def build_pdf(text: str) -> bytes:
    """Render ``text`` into a one-page PDF and return the raw bytes."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    buffer = io.BytesIO()
    with PdfPages(buffer) as pdf:
        lines = text.splitlines()
        # Split long documents over several pages, 62 lines per page.
        chunks = [lines[i : i + 62] for i in range(0, len(lines), 62)] or [lines]
        for chunk in chunks:
            fig = plt.figure(figsize=(8.27, 11.69))
            fig.text(
                0.06,
                0.95,
                "\n".join(chunk),
                va="top",
                ha="left",
                fontsize=7.2,
                family="monospace",
                linespacing=1.45,
            )
            pdf.savefig(fig)
            plt.close(fig)
    return buffer.getvalue()


def empty_pdf() -> bytes:
    """A structurally valid PDF that contains no text at all."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    buffer = io.BytesIO()
    with PdfPages(buffer) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        fig.patch.set_facecolor("white")
        pdf.savefig(fig)
        plt.close(fig)
    return buffer.getvalue()


def not_a_pdf() -> bytes:
    """A plain text file that merely has a .pdf name."""
    return b"This is definitely not a PDF file, it is plain text. " * 5


def corrupted_pdf() -> bytes:
    """A file that starts like a PDF but is damaged."""
    return b"%PDF-1.4\n" + b"\x00\x01\x02 broken binary content " * 40


def sample_pdf_bytes() -> bytes:
    return build_pdf(SAMPLE_RESUME)


def minimal_pdf_bytes() -> bytes:
    return build_pdf(MINIMAL_RESUME)


def no_skills_pdf_bytes() -> bytes:
    return build_pdf(NO_SKILLS_RESUME)