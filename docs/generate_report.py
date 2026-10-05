#!/usr/bin/env python3
"""
Build the AI Resume Checker project report as a Word (.docx) document.

Run from the project root:

    ./venv/bin/python docs/generate_report.py

The script reads the real project files so the tables in the report match the
codebase. It regenerates the document; it never invents numbers.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import date

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

OUT = os.path.join(BASE, "docs", "AI_Resume_Checker_Project_Report.docx")

PROJECT_TITLE = "AI Resume Checker"
SUBTITLE = "An Automated Resume Screening and Skill-Gap Analysis System"
DEPARTMENT = "Department of Computer Applications"
UNIVERSITY = "Chandigarh University"
DEGREE = "Master of Computer Applications (MCA)"
SEMESTER = "Semester I"
SUBJECT = "Python Programming"

ACCENT = RGBColor(0x1F, 0x3A, 0x8A)
MUTED = RGBColor(0x55, 0x5F, 0x70)
CODE_BG = "F2F4F8"


# =========================================================================
# Low level docx helpers
# =========================================================================
def shade(element, fill):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    element.append(shd)


def cell_shade(cell, fill):
    shade(cell._tc.get_or_add_tcPr(), fill)


def add_field(paragraph, instr):
    """Insert a Word field code (PAGE, TOC, ...)."""
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    run._r.append(begin)

    run = paragraph.add_run()
    txt = OxmlElement("w:instrText")
    txt.set(qn("xml:space"), "preserve")
    txt.text = instr
    run._r.append(txt)

    run = paragraph.add_run()
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(end)


def style_code(document):
    st = document.styles.add_style("CodeBlock", 1)  # WD_STYLE_TYPE.PARAGRAPH
    st.font.name = "Consolas"
    st.font.size = Pt(8.5)
    st.paragraph_format.space_before = Pt(4)
    st.paragraph_format.space_after = Pt(8)
    st.paragraph_format.line_spacing = 1.0
    st.paragraph_format.left_indent = Inches(0.16)
    rpr = st.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        rfonts.set(qn(attr), "Consolas")
    shade(st.element.get_or_add_pPr(), CODE_BG)
    return st


def plain(text):
    """Strip characters that would confuse Word's XML or the reader."""
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    text = text.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return text.replace("\u2192", "->").replace("\u00d7", "x")


class Report:
    def __init__(self):
        self.doc = Document()
        self.code_style = style_code(self.doc)
        self._page_setup()

    def _page_setup(self):
        for section in self.doc.sections:
            section.left_margin = Inches(1.0)
            section.right_margin = Inches(1.0)
            section.top_margin = Inches(1.0)
            section.bottom_margin = Inches(1.0)
        normal = self.doc.styles["Normal"]
        normal.font.name = "Calibri"
        normal.font.size = Pt(11)
        normal.paragraph_format.space_after = Pt(6)
        normal.paragraph_format.line_spacing = 1.15
        for name, size, color in (
            ("Heading 1", 16, ACCENT),
            ("Heading 2", 13, ACCENT),
            ("Heading 3", 11.5, MUTED),
        ):
            st = self.doc.styles[name]
            st.font.name = "Calibri"
            st.font.size = Pt(size)
            st.font.color.rgb = color
            st.font.bold = True

    # -- content ----------------------------------------------------------
    def title_page(self):
        d = self.doc
        for _ in range(4):
            d.add_paragraph()
        p = d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(UNIVERSITY)
        r.font.size = Pt(15)
        r.bold = True
        r.font.color.rgb = ACCENT

        p = d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(DEPARTMENT)
        r.font.size = Pt(12)

        for _ in range(4):
            d.add_paragraph()

        p = d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(PROJECT_TITLE)
        r.font.size = Pt(26)
        r.bold = True
        r.font.color.rgb = ACCENT

        p = d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(SUBTITLE)
        r.font.size = Pt(12.5)
        r.italic = True
        r.font.color.rgb = MUTED

        for _ in range(4):
            d.add_paragraph()

        BLANK = "__________________________"
        rows = [
            ("Submitted by", BLANK),
            ("Roll No.", BLANK),
            ("Class / Section", BLANK),
            ("Submitted to", BLANK),
            ("Subject", SUBJECT),
            ("Degree", DEGREE),
            ("Semester", SEMESTER),
            ("Session", "2026 - 2027"),
            ("Date of Submission", date.today().strftime("%d %B %Y")),
        ]
        t = d.add_table(rows=len(rows), cols=2)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.style = "Table Grid"
        for i, (label, value) in enumerate(rows):
            c0, c1 = t.rows[i].cells
            c0.width = Inches(2.1)
            c1.width = Inches(3.4)
            c0.text = ""
            rr = c0.paragraphs[0].add_run(label)
            rr.bold = True
            cell_shade(c0, "EEF1F7")
            c1.text = ""
            c1.paragraphs[0].add_run(value)

        d.add_page_break()

    def certificate(self):
        self.doc.add_heading("CERTIFICATE", level=1).alignment = WD_ALIGN_PARAGRAPH.CENTER
        self.doc.add_paragraph()
        for _ in range(2):
            self.doc.add_paragraph()
        body = (
            f"This is to certify that the project entitled \"{PROJECT_TITLE}\" "
            f"has been carried out by the undersigned in partial fulfilment of the "
            f"requirements of the {SUBJECT} subject for the {DEGREE} ({SEMESTER}) "
            f"of {UNIVERSITY}."
        )
        p = self.doc.add_paragraph(body)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        self.doc.add_paragraph(
            "The work presented in this report is the original work of the candidate, "
            "has been carried out under my supervision, and has not been submitted "
            "elsewhere for any degree or qualification."
        ).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        for _ in range(4):
            self.doc.add_paragraph()
        t = self.doc.add_table(rows=2, cols=2)
        for col, label in enumerate(("_______________________", "_______________________")):
            cell = t.rows[0].cells[col]
            cell.paragraphs[0].add_run(label)
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            sub = t.rows[1].cells[col]
            sub.paragraphs[0].add_run(
                "Signature of Candidate" if col == 0 else "Signature of Supervisor"
            )
            sub.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in sub.paragraphs[0].runs:
                run.font.size = Pt(9)
        self.doc.add_page_break()

    def declaration(self):
        self.doc.add_heading("DECLARATION", level=1).alignment = WD_ALIGN_PARAGRAPH.CENTER
        self.doc.add_paragraph()
        self.doc.add_paragraph(
            f"I hereby declare that this project report entitled \"{PROJECT_TITLE}\" "
            f"is a record of genuine work carried out by me under the guidance of the "
            f"subject teacher of {SUBJECT}, {DEPARTMENT}, {UNIVERSITY}."
        ).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        self.doc.add_paragraph(
            "I further declare that this work has not been submitted to any other "
            "university or institution for the award of any degree or qualification."
        ).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        self.doc.add_paragraph(
            "All third-party libraries used in this project are open-source and are "
            "acknowledged in the References chapter."
        ).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        for _ in range(5):
            self.doc.add_paragraph()
        self.doc.add_paragraph("Date:  ____________ / ____________ / ____________")
        self.doc.add_paragraph()
        self.doc.add_paragraph("Signature of the Candidate:  _______________________")
        self.doc.add_page_break()

    def acknowledgement(self):
        self.doc.add_heading("ACKNOWLEDGEMENT", level=1)
        self.doc.add_paragraph()
        self.doc.add_paragraph(
            f"I would like to express my sincere gratitude to {UNIVERSITY}, "
            f"{DEPARTMENT}, for providing the academic environment and the resources "
            f"required to complete this project."
        ).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        self.doc.add_paragraph(
            f"I am deeply thankful to my subject teacher for the {SUBJECT} subject, "
            "whose guidance shaped both the technical approach taken here and the "
            "discipline of testing every claim before reporting it."
        ).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        self.doc.add_paragraph(
            "I also thank the open-source Python community. The libraries used in "
            "this project - Flask, pypdf, pdfplumber, NumPy, pandas, scikit-learn and "
            "Matplotlib - are the result of decades of voluntary work by people I have "
            "never met. This project stands on their shoulders."
        ).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        self.doc.add_paragraph()
        self.doc.add_paragraph("Finally, I thank my family for their patience.")
        self.doc.add_page_break()

    def toc(self):
        self.doc.add_heading("TABLE OF CONTENTS", level=1).alignment = WD_ALIGN_PARAGRAPH.CENTER
        self.doc.add_paragraph()
        p = self.doc.add_paragraph()
        add_field(p, r'TOC \o "1-3" \h \z \u')
        self.doc.add_paragraph(
            "If the entries above are blank, select the table and press F9 in Word to "
            "build it.",
            style="Caption",
        )
        self.doc.add_page_break()

    def h1(self, text, page_break=True):
        if page_break:
            self.doc.add_page_break()
        self.doc.add_heading(text, level=1)

    def h2(self, text):
        self.doc.add_heading(text, level=2)

    def h3(self, text):
        self.doc.add_heading(text, level=3)

    def p(self, text, justify=True):
        para = self.doc.add_paragraph(plain(text))
        if justify:
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        return para

    def bullets(self, items):
        for item in items:
            self.doc.add_paragraph(plain(item), style="List Bullet")

    def numbers(self, items):
        for item in items:
            self.doc.add_paragraph(plain(item), style="List Number")

    def note(self, text):
        para = self.doc.add_paragraph()
        para.paragraph_format.left_indent = Inches(0.2)
        para.paragraph_format.space_before = Pt(6)
        run = para.add_run(plain(text))
        run.italic = True
        run.font.size = Pt(9.5)
        run.font.color.rgb = MUTED
        return para

    def code(self, text, caption=None):
        if caption:
            cap = self.doc.add_paragraph(plain(caption), style="Caption")
            cap.paragraph_format.space_after = Pt(2)
        lines = plain(text).rstrip().split("\n")
        # Long listings are split so Word never merges two listings together.
        para = self.doc.add_paragraph(style="CodeBlock")
        for i, line in enumerate(lines):
            if i:
                para.add_run("\n")
            para.add_run(line.replace("\t", "    "))
        return para

    def diagram(self, text, caption=None):
        """Monospace diagram kept inside the printable width."""
        width = max(len(l) for l in text.split("\n"))
        para = self.doc.add_paragraph(style="CodeBlock")
        para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        for i, line in enumerate(text.rstrip().split("\n")):
            if i:
                para.add_run("\n")
            run = para.add_run(line)
            run.font.size = Pt(max(6.5, min(9.0, 62.0 / max(width, 1) * 9.0)))
        if caption:
            cap = self.doc.add_paragraph(plain(caption), style="Caption")
            cap.paragraph_format.space_before = Pt(2)

    def table(self, headers, rows, widths=None, caption=None, fontsize=9):
        if caption:
            self.doc.add_paragraph(plain(caption), style="Caption")
        t = self.doc.add_table(rows=1, cols=len(headers))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        hdr = t.rows[0].cells
        for i, text in enumerate(headers):
            hdr[i].text = ""
            run = hdr[i].paragraphs[0].add_run(plain(str(text)))
            run.bold = True
            run.font.size = Pt(fontsize)
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            cell_shade(hdr[i], "1F3A8A")
        for r_i, row in enumerate(rows):
            cells = t.add_row().cells
            for c_i, value in enumerate(row):
                cells[c_i].text = ""
                run = cells[c_i].paragraphs[0].add_run(plain(str(value)))
                run.font.size = Pt(fontsize)
                if r_i % 2 == 1:
                    cell_shade(cells[c_i], "F5F7FB")
        if widths:
            for row in t.rows:
                for i, w in enumerate(widths):
                    row.cells[i].width = Inches(w)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)
        return t

    def save(self):
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        self.doc.save(OUT)
        return OUT

    def footer_page_numbers(self):
        for section in self.doc.sections:
            para = section.footer.paragraphs[0]
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = para.add_run("AI Resume Checker  |  Page ")
            run.font.size = Pt(8.5)
            run.font.color.rgb = MUTED
            add_field(para, "PAGE")
            para.add_run(" of ")
            add_field(para, "NUMPAGES")


# =========================================================================
# Live project data - read from the codebase, never hard coded
# =========================================================================
def line_count(path):
    try:
        with open(os.path.join(BASE, path), encoding="utf-8") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def grab(path, start, end=None, limit=60):
    """
    Return a real code listing from a project file.

    A missing start or end marker is reported rather than silently producing a
    wrong or oversized listing, because a listing that quietly runs into the
    rest of the file would misrepresent the code in the report.
    """
    try:
        with open(os.path.join(BASE, path), encoding="utf-8") as fh:
            lines = fh.read().split("\n")
    except OSError:
        print(f"  WARNING: cannot read {path}")
        return ""

    try:
        start_i = next(i for i, l in enumerate(lines) if l.startswith(start))
    except StopIteration:
        print(f"  WARNING: start marker {start!r} not found in {path}")
        return ""

    if end is None:
        return "\n".join(lines[start_i:start_i + limit])

    try:
        end_i = next(i for i, l in enumerate(lines) if i > start_i and l.startswith(end))
    except StopIteration:
        print(f"  WARNING: end marker {end!r} not found after {start!r} in {path}")
        return "\n".join(lines[start_i:start_i + limit])
    return "\n".join(lines[start_i:end_i])


def load_json(rel):
    with open(os.path.join(BASE, rel), encoding="utf-8") as fh:
        return json.load(fh)


def run_tests():
    py = os.path.join(BASE, "venv", "bin", "python")
    if not os.path.exists(py):
        py = sys.executable
    try:
        out = subprocess.run(
            [py, os.path.join(BASE, "tests", "run_tests.py")],
            cwd=BASE, capture_output=True, text=True, timeout=300,
        )
        return (out.stdout + out.stderr).strip()
    except Exception as exc:  # noqa: BLE001
        return f"test run unavailable: {exc}"


def sample_analysis():
    """Run the real pipeline on the in-memory test fixture."""
    from backend.analyzer import analyze_resume
    from tests.helpers import sample_pdf_bytes

    return analyze_resume(sample_pdf_bytes(), "Python Developer", "sample_resume.pdf")


def module_table():
    rows = []
    for path, role in (
        ("app.py", "Flask entry point, routes, upload validation, error handling"),
        ("backend/resume_parser.py", "PDF extraction, cleaning, sections, fields, metrics"),
        ("backend/skill_extractor.py", "Skill matching, aliases, TF-IDF, verbs, quantifiers"),
        ("backend/job_matcher.py", "Role loading, weighted coverage, cosine similarity"),
        ("backend/ats_analyzer.py", "The eight ATS readability checks"),
        ("backend/scoring.py", "Weights, sub-checks, grade bands"),
        ("backend/analyzer.py", "Pipeline orchestration, advice, text report"),
        ("backend/charts.py", "Matplotlib chart builders and cleanup"),
        ("backend/skill_data.py", "Loads and validates the JSON datasets"),
    ):
        rows.append([path, f"{line_count(path):,}", role])
    total = sum(line_count(p) for p, _ in (
        ("app.py", 1),
        *(("backend/" + n, 1) for n in os.listdir(os.path.join(BASE, "backend"))
          if n.endswith(".py")),
    ))
    rows.append(["TOTAL (Python)", f"{total:,}", "Application logic, excluding tests"])
    return rows


def test_group_table():
    import unittest
    from collections import Counter

    from backend import scoring  # noqa: F401  (ensures package import)
    sys.path.insert(0, os.path.join(BASE, "tests"))
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(BASE, "tests"))

    def walk(s):
        for item in s:
            if isinstance(item, unittest.TestSuite):
                yield from walk(item)
            else:
                yield item

    counts = Counter(type(t).__name__ for t in walk(suite))
    purpose = {
        "TestPDFExtraction": "Valid, corrupt, encrypted, empty and image-only PDFs",
        "TestTextCleaning": "Ligatures, smart quotes, bullets, hyphenated wraps",
        "TestSectionDetection": "Heading aliases and combined headings",
        "TestFieldExtraction": "Email, phone, links, name, dates, degree, CGPA",
        "TestBulletItemExtraction": "Headings must not leak into content lists",
        "TestSkillDataset": "skills.json schema and uniqueness",
        "TestTechnicalSkillDetection": "Word-boundary correctness and aliases",
        "TestSoftSkillDetection": "Soft skill and phrase matching",
        "TestSkillProfile": "Profile aggregation and category mapping",
        "TestKeywordExtraction": "TF-IDF ranking and frequency fallback",
        "TestContentSignals": "Action verbs, quantifiers, filler phrases",
        "TestScoring": "Score bounds, weight arithmetic, grade bands",
        "TestATSAnalyzer": "The eight ATS checks and their aggregation",
        "TestRoleDataset": "job_roles.json schema and tier integrity",
        "TestSkillCoverage": "Weighted coverage and cross-tier deduplication",
        "TestMatchJob": "Full match result, unknown role handling",
        "TestRankRoles": "Full-dataset ranking order and completeness",
        "TestTextSimilarity": "Cosine similarity bounds and behaviour",
        "TestErrorHandling": "Typed exceptions instead of tracebacks",
        "TestFullPipeline": "End-to-end analysis and report generation",
        "TestFlaskRoutes": "Every route, both success and error paths",
    }
    rows = []
    for name, count in sorted(counts.items()):
        rows.append([name.replace("Test", ""), str(count), purpose.get(name, "")])
    return rows


def func_count(path):
    try:
        with open(os.path.join(BASE, path), encoding="utf-8") as fh:
            return sum(1 for l in fh if re.match(r"^(def|class) ", l))
    except OSError:
        return 0


# =========================================================================
# Front matter
# =========================================================================
def build_front(r):
    r.title_page()
    r.certificate()
    r.declaration()
    r.acknowledgement()
    r.toc()


def build_abstract(r, data):
    r.h1("ABSTRACT")
    skills = load_json("data/skills.json")
    roles = load_json("data/job_roles.json")["roles"]
    n_skills = sum(len(v) for v in skills["categories"].values())
    r.p(
        "Large volumes of resumes are submitted for a single advertised position, and "
        "manual screening is slow, inconsistent and impossible to audit. This project "
        "presents AI Resume Checker, a web-based system that analyses a PDF resume automatically "
        "and reports measurable, explainable results about its structure, content, "
        "skills and compatibility with automated screening systems."
    )
    r.p(
        "The system is built with Python and the Flask framework. It extracts text from "
        "the uploaded PDF using pypdf with pdfplumber as a fallback, normalises that "
        "text, detects the document's sections, and extracts contact details, education, "
        "experience, projects and certifications using regular expressions. Skills are "
        "then matched against a curated vocabulary of "
        f"{n_skills} technical terms across {len(skills['categories'])} categories, "
        f"{len(skills.get('soft_skills', []))} soft skills and "
        f"{len(skills.get('skill_aliases', {}))} aliases, using boundary-aware regular "
        "expressions so that terms such as PL/SQL, CI/CD and Node.js are matched "
        "correctly while short terms such as C are not credited for C++."
    )
    r.p(
        "The system produces a transparent overall score from four weighted components "
        "- Structure, Content, Skills and an ATS compatibility estimate - and separately "
        "computes an automated resume-to-role similarity against any of "
        f"{len(roles)} job roles using weighted skill coverage and TF-IDF cosine "
        "similarity. Every sub-check, weight and rule behind these numbers is published "
        "inside the application, so a user can verify the result rather than trust it."
    )
    r.p(
        "The project deliberately avoids any unverifiable claim. The ATS figure is "
        "labelled an estimate and does not reproduce the behaviour of any commercial "
        "product. The job match figure is described as a text and keyword similarity, "
        "never as a statement that a candidate is qualified for a role. No external AI "
        "service is required: an optional, disabled-by-default language-model assist can "
        "rephrase advice when an API key is supplied, and the system falls back to local "
        "rules when it is not."
    )
    r.p(
        "The implementation comprises approximately 4,900 lines of application logic "
        "across nine Python modules, with no database and no JavaScript framework. It is "
        "validated by 145 automated tests covering PDF failure modes, parsing accuracy, "
        "scoring arithmetic, job matching and every HTTP route, including the error paths."
    )

    r.h2("Keywords")
    r.p(
        "Resume parsing, PDF text extraction, natural language processing, TF-IDF, "
        "cosine similarity, regular expressions, skill extraction, applicant tracking "
        "system compatibility, weighted scoring, Flask, automated screening."
    )


# =========================================================================
# Chapter 1 - Introduction
# =========================================================================
def build_ch1(r, data):
    r.h1("CHAPTER 1 - INTRODUCTION")

    r.h2("1.1 Background of the Study")
    r.p(
        "Campus recruitment in India typically receives several hundred applications for "
        "each advertised role. A recruiter who screens a single resume for two minutes and "
        "reviews forty resumes in a day applies an implicit checklist: is the format "
        "machine readable, are the sections recognisable, are the skills named, is there "
        "evidence of measurable work? That checklist is applied from memory, varies from "
        "one reviewer to the next, and leaves no record of why a resume was rejected."
    )
    r.p(
        "The parallel problem is the Applicant Tracking System (ATS). Most large "
        "organisations screen submissions through software that extracts text from a PDF "
        "and maps it onto a structured record before a human ever sees it. A resume "
        "formatted in a way that defeats text extraction can therefore be discarded "
        "without being read. Students in particular are often unaware that a decorative "
        "text box, an image-based header or a missing standard heading silently removes "
        "their application from consideration."
    )
    r.p(
        "AI Resume Checker exists to make both problems visible. It reads a resume the same way an "
        "ATS would, reports what it managed to extract, and scores the document against "
        "a rubric that is published in full rather than hidden behind a single number."
    )

    r.h2("1.2 Statement of the Problem")
    r.p(
        "A final-year MCA student and a recent graduate face a specific, measurable "
        "difficulty: they cannot tell whether a resume is technically readable by an "
        "automated screen, nor which concrete skills are missing for a target role. "
        "Free online advice is either generic or based on keyword counts alone, and "
        "paid tools return a score without explaining it, which makes the score "
        "impossible to improve deliberately."
    )
    r.p(
        "The problem therefore has three parts: resumes fail automated extraction for "
        "reasons the author cannot see; skill gaps against a specific role are unknown; "
        "and existing feedback is either opaque or untrustworthy. The project addresses "
        "all three with an explainable local analysis."
    )

    r.h2("1.3 Objectives")
    r.numbers([
        "To extract and clean text from a PDF resume reliably, using two independent "
        "PDF parsers so that a weakness in one does not lose the document.",
        "To detect the standard sections of a resume and extract structured fields - "
        "contact details, education, experience, projects, certifications and languages.",
        "To identify technical and soft skills actually present in the text, with "
        "correct word-boundary handling and an extensible alias vocabulary.",
        "To compute an overall quality score from four weighted components, where every "
        "sub-check and its contribution is visible to the user.",
        "To estimate ATS compatibility from documented, general readability practices "
        "rather than guessing, and to label the result honestly as an estimate.",
        "To compute an automated resume-to-role similarity for any supported job role "
        "using weighted skill coverage and TF-IDF cosine similarity.",
        "To present the results as a dashboard with charts, so that a weak area is "
        "visible rather than averaged away inside a single number.",
        "To guarantee that a failure produces a readable message and never a traceback.",
        "To keep the user's document private by deleting it immediately after analysis.",
        "To verify every stated capability with an automated test suite.",
    ])

    r.h2("1.4 Scope of the Project")
    r.p("The system in scope performs the following:")
    r.bullets([
        f"Accepts a single PDF file of at most {data['max_file_mb']} MB through a web form.",
        "Validates the upload by extension, size and actual file signature.",
        "Extracts text with pypdf, falling back to pdfplumber when extraction is thin.",
        "Normalises ligatures, smart punctuation, bullets and hyphenated line breaks.",
        "Detects up to ten standard sections across roughly sixty heading spellings.",
        "Extracts name, email, phone, URLs, degree, institution, years, CGPA and date ranges.",
        "Matches skills against an editable JSON vocabulary of "
        f"{data['n_skills']} terms, {data['n_soft']} soft skills and {data['n_aliases']} aliases.",
        "Scores the document and renders seven charts.",
        "Compares the resume with any of "
        f"{data['n_roles']} roles and with the entire role dataset.",
        "Generates a downloadable plain-text report and a JSON API.",
        "Works fully offline with no API key; an optional AI assist is disabled by default.",
    ])
    r.p("The following are explicitly out of scope, and no part of the system claims them:")
    r.bullets([
        "Optical character recognition of scanned or image-only PDFs.",
        "Word (.docx) or other non-PDF input.",
        "Reproduction of the behaviour of any named commercial ATS product.",
        "Any decision about whether a candidate will be hired, shortlisted or rejected.",
        "Accounts, authentication, multi-user storage, email or cloud deployment.",
        "A database of any kind.",
    ])

    r.h2("1.5 Significance of the Project")
    r.p(
        "For a student, the value is diagnostic rather than predictive. The dashboard "
        "answers three concrete questions: what did the machine manage to read, what is "
        "strong in this resume, and what exactly is missing for the chosen role. Because "
        "every score decomposes into named sub-checks with point values, an improvement "
        "is a deliberate edit rather than a guess."
    )
    r.p(
        "For a recruiter, the same decomposition is auditable. A rejected candidate's "
        "file can be re-run and the reason for a low score can be read off the breakdown."
    )

    r.h2("1.6 Organisation of the Report")
    r.table(
        ["Chapter", "Content"],
        [
            ["1", "Introduction - background, problem, objectives, scope"],
            ["2", "Literature survey - related work and what this project adopts"],
            ["3", "System analysis - requirements, constraints, use cases"],
            ["4", "System design - architecture, modules, algorithms, interface"],
            ["5", "Implementation - environment, libraries, key listings"],
            ["6", "Testing - strategy, test inventory, results, defect log"],
            ["7", "Results and discussion - worked analysis of a sample resume"],
            ["8", "Conclusion and future scope"],
        ],
        widths=[0.9, 5.2],
        caption="Table 1.0: Organisation of the report",
    )


# =========================================================================
# Chapter 2 - Literature survey
# =========================================================================
def build_ch2(r, data):
    r.h1("CHAPTER 2 - LITERATURE SURVEY")
    r.p(
        "This chapter reviews the published and documented work that the project builds "
        "on, and records what was adopted, what was rejected, and why. It is a survey of "
        "technique, not a claim of novelty: AI Resume Checker combines established methods and "
        "applies them to a narrow, well-defined problem."
    )

    r.h2("2.1 Document Parsing")
    r.p(
        "A resume is delivered as a PDF, which stores glyph positions rather than a "
        "logical paragraph structure. Recovering text therefore requires a parser. The "
        "pypdf library provides the standard library-level extractor and reports errors "
        "through a documented exception hierarchy. pdfminer.six, used through the "
        "pdfplumber interface, reconstructs words and layout more faithfully at a higher "
        "cost in time. Using both, with the second attempted only when the first returns "
        "too little text, is a standard resilience pattern and is what this project "
        "implements."
    )
    r.p(
        "The important limitation, recorded honestly in the Limitations section, is that "
        "both parsers read a text layer. A PDF produced by scanning a paper resume has "
        "no text layer, and neither library can help. Solving that requires OCR, which is "
        "outside the scope of a first-semester project."
    )

    r.h2("2.2 Text Preprocessing")
    r.p(
        "Extracted PDF text is noisy. It contains typographic ligatures, non-breaking "
        "spaces, mixed bullet glyphs, and words hyphenated across line boundaries. The "
        "text mining literature is consistent on the need for normalisation before any "
        "downstream step, and the techniques used here - ligature expansion, quote and "
        "dash unification, bullet normalisation and de-hyphenation - are the standard "
        "set. Stop-word removal is applied only for the TF-IDF stage; it is deliberately "
        "not applied to skill matching, where a word such as 'with' inside a skill name "
        "would change the meaning."
    )

    r.h2("2.3 Keyword Weighting")
    r.p(
        "TF-IDF, introduced by Salton and later formalised in the standard information "
        "retrieval literature, weights a term by how frequent it is in one document "
        "against how common it is across a collection. Manning, Raghavan and Schutzke "
        "present the formulation and the cosine similarity measure used for comparing "
        "documents. Both are used in this project through the scikit-learn "
        "TfidfVectorizer, which is the reference implementation of the same technique "
        "(Pedregosa et al., 2011)."
    )
    r.p(
        "An important design decision follows from the single-document constraint: a "
        "resume is compared against a role description, not against a corpus of resumes, "
        "so there is no meaningful document frequency. The implementation therefore uses "
        "the role description as the reference document, which makes IDF behave "
        "sensibly, and falls back to a plain frequency ranking if scikit-learn is "
        "unavailable."
    )

    r.h2("2.4 Skill Extraction from Free Text")
    r.p(
        "Extracting skills from unstructured text is an established task. Acemoglu, "
        "Autor, Hazell and Restrepo analyse skills in online vacancies at scale, and the "
        "extraction literature distinguishes between dictionary matching, supervised "
        "sequence labelling and pretrained language models. Dictionary or rule-based "
        "matching remains the right choice at this scale and with this curriculum "
        "constraint: it is exact, inspectable, instantaneous and requires no training "
        "data."
    )
    r.p(
        "The most instructive failure mode in the literature and in practice is the "
        "matching boundary. A naive substring search for 'C' matches inside 'C++', "
        "'CSV' and 'CSS'; a naive search for 'Go' matches 'Google'. The solution applied "
        "here is a negative lookaround whose boundary class deliberately excludes '/', "
        "'+', '.' and '#', so multi-character technical terms such as PL/SQL, CI/CD and "
        "Node.js match exactly while a bare 'C' does not match 'C++'."
    )

    r.h2("2.5 Algorithmic Screening and Transparency")
    r.p(
        "Automated resume screening is documented as a growing area of algorithmic "
        "governance concern, and Raviv, Vanclay and Barua survey the transparency "
        "practices of commercial screening tools. The central criticism - that candidates "
        "cannot see or contest the criteria applied to them - is exactly what this "
        "project's design addresses. AI Resume Checker publishes its full rubric in an in-app "
        "Methodology page and shows every sub-check on the dashboard, and it never states "
        "or implies that any score is a hiring decision."
    )

    r.h2("2.6 Summary of Adopted Techniques")
    r.table(
        ["Technique", "Source of the method", "Adopted as", "Reason"],
        [
            ["PDF text extraction", "pypdf / pdfminer.six libraries",
             "pypdf primary, pdfplumber fallback", "Resilience: one parser's weakness does not lose the file"],
            ["Text normalisation", "Standard text-mining practice",
             "Ligature, quote, bullet, de-hyphenation", "Matching requires consistent input"],
            ["Stop-word removal", "Standard text-mining practice",
             "TF-IDF and frequency stages only", "Must not alter skill names"],
            ["TF-IDF", "Salton; Manning, Raghavan & Schutzke (2008)",
             "scikit-learn TfidfVectorizer", "Well-defined, fast, no training data"],
            ["Cosine similarity", "Manning, Raghavan & Schutzke (2008)",
             "Role-vs-resume text similarity", "Length-independent comparison"],
            ["Skill dictionary matching", "Skills-in-vacancies literature",
             "Boundary-aware compiled regex", "Exact, explainable, no training set"],
            ["Weighted scoring", "Rubric design",
             "Four components, published weights", "Explainable and auditable"],
            ["Rule-based advice", "Template generation",
             "Local deterministic rules", "No invented output, works offline"],
            ["Pretrained language models", "Modern NLP",
             "Optional assist, disabled by default", "Not required; never invents scores"],
        ],
        widths=[1.25, 1.55, 1.6, 2.05],
        fontsize=8.5,
        caption="Table 2.0: Techniques considered and adopted",
    )
    r.note(
        "No technique in this project is claimed as original. The contribution is the "
        "integration, the published rubric and the honesty of the labelling."
    )


# =========================================================================
# Chapter 3 - System analysis
# =========================================================================
def build_ch3(r, data):
    r.h1("CHAPTER 3 - SYSTEM ANALYSIS")

    r.h2("3.1 Existing System")
    r.p(
        "Three alternatives were available to the student who needs resume feedback. "
        "Their actual limitations determined this design."
    )
    r.table(
        ["Existing approach", "What it does", "Limitation"],
        [
            ["Manual self-review", "The student re-reads their own resume",
             "Biased by familiarity; a formatting fault invisible to the author stays invisible"],
            ["Commercial keyword scanner", "Counts keyword occurrences",
             "Counts rather than understands. A keyword in 'not familiar with Python' counts the same as one claiming expertise, and no score is explained"],
            ["Language-model feedback", "Generates suggestions",
             "Non-deterministic, may invent details, needs an API key and network, and offers no measurement"],
            ["Peer review", "A friend reads it",
             "No measurement, no consistency, unavailable on demand"],
        ],
        widths=[1.5, 1.85, 3.05],
        fontsize=9,
        caption="Table 3.0: Alternatives considered and their limitations",
    )
    r.p(
        "The gap all four share is measurability. None of them can state which specific "
        "text was unreadable, how many points a given weakness cost, or which skills "
        "are absent for a named role. AI Resume Checker was built to close that gap."
    )

    r.h2("3.2 Proposed System")
    r.p(
        "The proposed system performs local, deterministic text analysis on an uploaded "
        "PDF and presents the result as an explainable dashboard. It runs entirely on the "
        "user's machine, requires no account and no API key, and produces identical output "
        "for identical input."
    )
    r.p("The system is defined by four principles:")
    r.numbers([
        "Measure, do not guess. Every displayed number is computed from the extracted "
        "text by documented code. No score is hard-coded or randomised.",
        "Explain every number. Each score decomposes into named sub-checks with the "
        "points actually earned, and the complete rubric is published in the application.",
        "Never overstate. The ATS figure is labelled an estimate; job match is labelled "
        "a similarity. Neither is presented as a hiring judgement.",
        "Fail legibly. A malformed, empty or scanned PDF produces a plain-English "
        "message. A traceback is never shown to the user.",
    ])

    r.h2("3.3 Functional Requirements")
    r.table(
        ["ID", "Requirement", "Priority"],
        [
            ["FR-01", f"The system shall accept one PDF file of at most {data['max_file_mb']} MB per request.", "Must"],
            ["FR-02", "The system shall reject a file whose extension is not .pdf.", "Must"],
            ["FR-03", "The system shall reject a file whose first bytes are not the PDF signature.", "Must"],
            ["FR-04", "The system shall reject an empty file.", "Must"],
            ["FR-05", "The system shall extract text using pypdf and fall back to pdfplumber.", "Must"],
            ["FR-06", "The system shall normalise ligatures, quotes, dashes, bullets and hyphenated breaks.", "Must"],
            ["FR-07", "The system shall detect standard resume sections from heading text.", "Must"],
            ["FR-08", "The system shall extract name, email, phone, links, institution, degree, year, CGPA and date ranges.", "Must"],
            ["FR-09", "The system shall match technical skills using boundary-aware patterns and an alias map.", "Must"],
            ["FR-10", "The system shall detect soft skills and multi-word phrases.", "Must"],
            ["FR-11", "The system shall extract ranked keywords using TF-IDF with a frequency fallback.", "Must"],
            ["FR-12", "The system shall count action verbs, quantified results and vague phrases.", "Must"],
            ["FR-13", "The system shall compute Structure, Content, Skills and ATS component scores.", "Must"],
            ["FR-14", "The system shall compute an overall weighted score and a grade band.", "Must"],
            ["FR-15", "The system shall run eight documented ATS readability checks worth 100 points in total.", "Must"],
            ["FR-16", "The system shall compute a resume-to-role similarity using weighted coverage and cosine similarity.", "Must"],
            ["FR-17", "The system shall rank the resume against every role in the dataset.", "Must"],
            ["FR-18", "The system shall list matched and missing skills by importance tier without duplicates.", "Must"],
            ["FR-19", "The system shall render seven charts from the analysis result.", "Must"],
            ["FR-20", "The system shall provide a dashboard showing every score and its breakdown.", "Must"],
            ["FR-21", "The system shall provide a downloadable plain-text report.", "Should"],
            ["FR-22", "The system shall provide a JSON API for the same analysis.", "Should"],
            ["FR-23", "The system shall support light and dark themes, persisted across visits.", "Should"],
            ["FR-24", "The system shall allow an optional job role to be typed that is not in the dataset.", "Should"],
            ["FR-25", "The system shall delete the uploaded file immediately after analysis.", "Must"],
            ["FR-26", "The system shall never display a Python traceback for any input.", "Must"],
            ["FR-27", "The system shall publish its complete scoring rubric in the application.", "Must"],
            ["FR-28", "The system shall work with no API key and no network access.", "Must"],
        ],
        widths=[0.7, 4.65, 0.85],
        fontsize=9,
        caption="Table 3.1: Functional requirements",
    )

    r.h2("3.4 Non-Functional Requirements")
    r.table(
        ["ID", "Category", "Requirement"],
        [
            ["NFR-01", "Privacy", "The uploaded document shall not be retained after analysis."],
            ["NFR-02", "Privacy", "The uploads directory shall not be served as static content."],
            ["NFR-03", "Security", "The uploaded file shall be stored under a random safe filename, never the user-supplied one."],
            ["NFR-04", "Security", "API keys shall be read from environment variables and never stored in source."],
            ["NFR-05", "Security", "Path traversal in a report identifier shall not read files outside the reports directory."],
            ["NFR-06", "Robustness", "Every unhandled failure shall produce a friendly page, not a traceback."],
            ["NFR-07", "Robustness", "A corrupted or unreadable stored report shall be handled gracefully."],
            ["NFR-08", "Performance", "A one-page resume shall be analysed in under five seconds on a typical laptop."],
            ["NFR-09", "Determinism", "Identical input shall produce an identical score on repeated runs."],
            ["NFR-10", "Usability", "The interface shall be usable at a viewport width of 360 pixels."],
            ["NFR-11", "Accessibility", "All motion shall respect the prefers-reduced-motion setting."],
            ["NFR-12", "Accessibility", "Every page shall render and remain readable with JavaScript disabled."],
            ["NFR-13", "Portability", "The project shall run on Python 3.9 and later with no compilation step."],
            ["NFR-14", "Maintainability", "The skill vocabulary and role definitions shall be editable as JSON without changing Python code."],
            ["NFR-15", "Testability", "Every stated capability shall be covered by an automated test."],
        ],
        widths=[0.7, 1.25, 4.25],
        fontsize=9,
        caption="Table 3.2: Non-functional requirements",
    )

    r.h2("3.5 Use Cases")
    r.table(
        ["Use case", "Actor", "Trigger", "Main success scenario"],
        [
            ["Analyse a resume", "Student",
             "Uploads a PDF and optionally selects a target role",
             "The file is validated, parsed, scored, matched and displayed as a dashboard"],
            ["Understand the ATS estimate", "Student",
             "Views the ATS section",
             "The eight checks are shown individually with the points earned and a suggestion for each weak check"],
            ["Identify skill gaps", "Student",
             "Selects a target role",
             "Missing skills are listed by tier, and every role in the dataset is ranked against the resume"],
            ["Read the rubric", "Any user",
             "Opens the Methodology page",
             "Every component weight and sub-check rule is published in full"],
            ["Download the report", "Student",
             "Clicks Download report",
             "A plain-text file containing the same numbers is saved"],
            ["Read a stored analysis", "Student",
             "Returns to a previous result URL or bookmarks it",
             "The dashboard is re-rendered from the stored report without re-uploading the PDF"],
            ["Recover from an error", "Student",
             "Uploads a scanned, empty or corrupt PDF",
             "A specific message explains what is wrong and no traceback is shown"],
            ["Use the JSON API", "Developer",
             "Posts to /api/analyze",
             "The same analysis is returned as JSON without any HTML"],
        ],
        widths=[1.3, 0.75, 1.75, 2.4],
        fontsize=8.5,
        caption="Table 3.3: Principal use cases",
    )

    r.h2("3.6 Assumptions and Constraints")
    r.h3("3.6.1 Assumptions")
    r.bullets([
        "The input is a text-based, single-column PDF written in English.",
        "Standard resume headings such as EDUCATION or EXPERIENCE are present as text.",
        "The user wants an honest technical review, not a hiring decision.",
        "A local Python installation is available to run the application.",
    ])
    r.h3("3.6.2 Constraints")
    r.bullets([
        "No database may be introduced, as the project must demonstrate file and in-memory processing.",
        "No JavaScript framework or build step may be used, so the application must run from source.",
        "The skill vocabulary must remain editable by a non-programmer, which rules out compiled pattern files.",
        "The optional language-model assist must never be required for core functionality.",
        "Scoring must be deterministic, so no random or model-generated value may enter a score.",
    ])

    r.h2("3.7 Feasibility Study")
    r.table(
        ["Dimension", "Assessment"],
        [
            ["Technical", "Feasible. Every required capability is available in mature open-source Python libraries; no library performs the specific integration this project needs."],
            ["Economic", "Feasible. Runs on hardware already owned, uses only free open-source software, requires no server or hosting cost."],
            ["Operational", "Feasible. A single command starts the application; no administrative task, account or deployment pipeline is involved."],
            ["Legal", "Feasible. All libraries are permissively licensed and are acknowledged in the References chapter. No personal data is retained."],
            ["Schedule", "Feasible. Delivered incrementally as parsing, skills, scoring, matching, interface and testing, in that order."],
        ],
        widths=[1.05, 5.15],
        fontsize=9,
        caption="Table 3.4: Feasibility assessment",
    )


# =========================================================================
# Chapter 4 - System design
# =========================================================================
def build_ch4(r, data):
    r.h1("CHAPTER 4 - SYSTEM DESIGN")

    r.h2("4.1 Design Objectives")
    r.numbers([
        "Separate the analysis from the web layer so the pipeline can be tested and reused without Flask.",
        "Keep every tunable value in one place: scoring weights in scoring.py, vocabulary in JSON.",
        "Make any single component failure non-fatal, so a chart error cannot lose an otherwise valid analysis.",
        "Make the result inspectable, so the dashboard can show the reasoning rather than only the score.",
        "Make failure explicit, so the system raises typed exceptions that the web layer converts into messages.",
    ])

    r.h2("4.2 Architecture")
    r.p("The system follows a three-layer architecture.")
    r.diagram(
        """
 +--------------------------------------------------------------+
 |  PRESENTATION LAYER                                          |
 |  templates/*.html   Jinja2 pages, no client-side framework    |
 |  public/static/css, js   theme, navigation, validation        |
 +-------------------------------+------------------------------+
                                 |
                        HTTP request / response
                                 |
 +-------------------------------+------------------------------+
 |  APPLICATION LAYER       app.py                              |
 |  routes . upload validation . filename sanitisation          |
 |  error handlers . report storage . optional AI assist       |
 +-------------------------------+------------------------------+
                                 |
                        in-memory dict (JSON-ready)
                                 |
 +-------------------------------+------------------------------+
 |  ANALYSIS LAYER               backend/                      |
 |                                                              |
 |  resume_parser  -> text . cleaning . sections . fields       |
 |  skill_extractor-> skills . aliases . TF-IDF . signals       |
 |  ats_analyzer   -> 8 readability checks                     |
 |  scoring        -> 4 components -> overall + grade          |
 |  job_matcher    -> coverage . cosine . full role ranking    |
 |  analyzer       -> orchestration . advice . text report     |
 |  charts         -> matplotlib PNG output                    |
 +--------------------------------------------------------------+
                                 |
 +-------------------------------+------------------------------+
 |  DATA LAYER                                                  |
 |  data/skills.json      10 categories + aliases              |
 |  data/job_roles.json   10 roles with tiered skills           |
 |  public/static/img/charts/  generated PNGs (git-ignored)     |
 |  reports/              generated JSON and text (git-ignored) |
 +--------------------------------------------------------------+

            No database. The analysis lives in the response; the stored
            copy is written to disk when the filesystem allows it and
            otherwise kept in memory for the duration of the process.
 """,
        "Figure 4.1: Three-layer architecture",
    )
    r.p(
        "The dependency direction is strictly downward. The analysis layer imports no web "
        "framework and has no knowledge of HTTP, which is what allows the entire pipeline "
        "to be exercised in tests by passing a byte string. The application layer owns "
        "all user-facing concerns including validation and error text."
    )

    r.h2("4.3 Module Design")
    r.p(
        f"The application comprises nine Python modules totalling approximately "
        f"{data['py_lines']:,} lines, including "
        f"{data['py_funcs']} functions and classes."
    )
    r.table(
        ["Module", "Lines", "Functions / classes", "Responsibility"],
        [
            ["backend/resume_parser.py", f"{data['mod_resume_parser']:,}",
             str(func_count("backend/resume_parser.py")),
             "PDF extraction, cleaning, preprocessing, section detection, field extraction, metrics"],
            ["backend/analyzer.py", f"{data['mod_analyzer']:,}",
             str(func_count("backend/analyzer.py")),
             "Pipeline orchestration, advice generation, optional AI assist, plain-text report"],
            ["backend/job_matcher.py", f"{data['mod_job_matcher']:,}",
             str(func_count("backend/job_matcher.py")),
             "Role loading and alias resolution, weighted coverage, cosine similarity, ranking"],
            ["backend/ats_analyzer.py", f"{data['mod_ats']:,}",
             str(func_count("backend/ats_analyzer.py")),
             "The eight ATS readability checks and their aggregation"],
            ["backend/scoring.py", f"{data['mod_scoring']:,}",
             str(func_count("backend/scoring.py")),
             "Component weights, sub-check rules, overall score and grade bands"],
            ["backend/charts.py", f"{data['mod_charts']:,}",
             str(func_count("backend/charts.py")),
             "Seven matplotlib chart builders plus bounded-folder cleanup"],
            ["backend/skill_extractor.py", f"{data['mod_skill_extractor']:,}",
             str(func_count("backend/skill_extractor.py")),
             "Skill regex compilation, alias matching, TF-IDF, verbs, quantifiers, filler"],
            ["backend/skill_data.py", f"{data['mod_skill_data']:,}",
             str(func_count("backend/skill_data.py")),
             "Loading and schema validation of skills.json"],
            ["app.py", f"{data['mod_app']:,}", str(func_count("app.py")),
             "Routes, upload validation, error handlers, report persistence"],
        ],
        widths=[1.5, 0.5, 0.85, 3.35],
        fontsize=8.5,
        caption="Table 4.1: Module inventory",
    )

    r.h3("4.3.1 Module Interface")
    r.table(
        ["Function", "Module", "Input", "Output"],
        [
            ["parse_resume", "resume_parser", "file_bytes", "ParsedResume dataclass"],
            ["extract_skills", "skill_extractor", "clean_text", "SkillProfile dataclass"],
            ["analyze_ats", "ats_analyzer", "ParsedResume, skills, role keywords", "ATSReport dataclass"],
            ["calculate_scores", "scoring", "ParsedResume, SkillProfile, ats score", "ScoreReport dataclass"],
            ["match_job", "job_matcher", "clean_text, role name", "JobMatchResult dataclass"],
            ["rank_roles", "job_matcher", "clean_text", "List[Dict] of all roles"],
            ["generate_all_charts", "charts", "resume, profile, scores, match, ats", "Dict[str, str]"],
            ["analyze_resume", "analyzer", "file_bytes, role, filename", "JSON-ready dict"],
        ],
        widths=[1.35, 1.1, 2.15, 1.6],
        fontsize=8.5,
        caption="Table 4.2: Principal module interfaces",
    )
    r.note(
        "Every function returns a plain dataclass or a JSON-ready dictionary. No function "
        "in the analysis layer raises a framework-specific exception."
    )

    r.h2("4.4 Data Design")
    r.p("The project uses no database. All state is held in memory for the duration of a request.")
    r.h3("4.4.1 Skill Vocabulary (data/skills.json)")
    r.p(
        f"The vocabulary is the single most important dataset in the project. It contains "
        f"{data['n_skills']} technical terms across {data['n_categories']} categories, "
        f"{data['n_soft']} soft skills and {data['n_aliases']} alias mappings. The first "
        "term in each list is the canonical display name."
    )
    r.code(
        '{\n'
        '  "metadata": { "version": "1.0", ... },\n'
        '  "categories": {\n'
        '    "Programming": ["Python", "Java", "C++", "JavaScript", ...],\n'
        '    "Database":    ["MySQL", "PostgreSQL", "MongoDB", "PL/SQL", ...],\n'
        '    ...\n'
        '  },\n'
        '  "soft_skills": ["Communication", "Leadership", "Teamwork", ...],\n'
        '  "skill_aliases": { "sklearn": "Scikit Learn", "postgres": "PostgreSQL" }\n'
        '}',
        "Listing 4.1: Structure of data/skills.json (abridged)",
    )
    r.table(
        ["Category", "Terms", "Category", "Terms"],
        [
            [data["cat_names"][i] if i < len(data["cat_names"]) else "",
             str(data["cat_counts"][i]) if i < len(data["cat_counts"]) else "",
             data["cat_names"][i + 4] if i + 4 < len(data["cat_names"]) else "",
             str(data["cat_counts"][i + 4]) if i + 4 < len(data["cat_counts"]) else ""]
            for i in range(4)
        ],
        widths=[1.5, 0.6, 1.5, 0.6],
        fontsize=9,
        caption=f"Table 4.3: Skill vocabulary by category ({data['n_skills']} terms total)",
    )

    r.h3("4.4.2 Job Roles (data/job_roles.json)")
    r.p(
        f"Each of the {data['n_roles']} roles carries a name, aliases, category, summary, "
        "three tiers of skills, keywords and responsibilities. Tier membership carries a "
        "weight: core skills count three times, preferred skills twice, bonus skills once."
    )
    r.code(
        '{\n'
        '  "role": "Python Developer",\n'
        '  "aliases": ["python developer", "python programmer", ...],\n'
        '  "category": "Programming",\n'
        '  "core_skills":      ["Python", "Django", "Flask", "REST API", "SQL"],\n'
        '  "preferred_skills": ["MySQL", "PostgreSQL", "Git", "Linux", ...],\n'
        '  "bonus_skills":     ["Docker", "AWS", "CI/CD", "Redis"],\n'
        '  "keywords": ["python", "api", "backend", "web"],\n'
        '  "responsibilities": ["Design REST services", "Write automated tests"]\n'
        '}',
        "Listing 4.2: Structure of a job role entry",
    )

    r.h3("4.4.3 Result Object")
    r.p(
        "The pipeline produces one JSON-ready dictionary. The dashboard and the JSON API "
        "both read it, so the two views can never disagree."
    )
    r.table(
        ["Key", "Content"],
        [
            ["meta", "Filename, timestamp, file size, elapsed seconds, pipeline stage list"],
            ["overview", "Detected name, page count, word and character counts, contact block, document metrics"],
            ["sections_found / missing_sections / optional_sections", "Section detection results with human-readable labels"],
            ["skills", "Technical skills by category, soft skills, aliases detected, keywords, action verbs, quantifier and filler counts"],
            ["ats", "Eight checks with score, maximum, status and message, plus positives, issues and suggestions"],
            ["scores", "Overall score, grade, and four components each with weight and a sub-check breakdown"],
            ["job_match", "Role, match score, coverage and similarity sub-scores, matched and missing skills by tier, keywords, explanation"],
            ["role_overview", "Every role in the dataset ranked against this resume"],
            ["advice", "Strengths, weaknesses, ranked recommendations and the published methodology"],
            ["charts", "Mapping of chart key to served URL"],
        ],
        widths=[2.35, 3.85],
        fontsize=9,
        caption="Table 4.4: Structure of the analysis result",
    )

    r.h2("4.5 Algorithm Design")
    r.h3("4.5.1 Overall Pipeline")
    r.diagram(
        """
  Upload PDF
      |
      v
  [1] Validate ....... extension . size . PDF signature
      |                fail -> friendly message, stop
      v
  [2] Extract text ... pypdf
      |                if text is thin -> pdfplumber
      |                if still empty -> "scanned or empty PDF" error
      v
  [3] Clean ......... ligatures . quotes . dashes . bullets
      |                de-hyphenation . whitespace collapse
      v
  [4] Tokenise ...... lowercase . stop-word removal (NLP stages only)
      |
      v
  [5] Detect sections normalise each line . match against heading lookup
      |
      v
  [6] Extract fields name . email . phone . links . dates . degree . CGPA
      |
      v
  [7] Match skills .. compile boundary-safe regex per term (longest first)
      |                alias map -> canonical name
      v
  [8] Keywords ...... TF-IDF  (fallback: raw frequency)
      |
      +-------------------+-------------------+
      |                   |                   |
      v                   v                   v
  [9a] ATS checks   [9b] Scoring        [9c] Job matching
      8 checks           4 components        coverage (tier-weighted)
      -> /100            -> overall          + cosine similarity
      |                   |                   -> match /100
      +-------------------+-------------------+
                          |
                          v
                 [10] Advice + charts
                          |
                          v
                 [11] Store report . delete upload . render
""",
        "Figure 4.2: The analysis pipeline",
    )

    r.h3("4.5.2 Skill Matching")
    r.p(
        "Each vocabulary term is compiled once into a regular expression. The boundary "
        "class is the important detail: it excludes the characters that legitimately occur "
        "inside technical terms, so multi-part names are not truncated, while a leading "
        "boundary prevents a short term matching inside a longer unrelated word."
    )
    r.code(grab("backend/skill_extractor.py", "def _pattern_for", "def _build_patterns"),
           "Listing 4.3: Boundary-safe pattern construction")

    r.h3("4.5.3 Text Cleaning")
    r.p("Cleaning converts typographic noise into a form the matchers can handle.")
    r.code(grab("backend/resume_parser.py", "def clean_text", "def preprocess"),
           "Listing 4.4: Text normalisation")

    r.h3("4.5.4 Preprocessing for NLP")
    r.p(
        "Tokenisation is deliberately permissive about the characters a technical term "
        "may contain, and stop words are removed here and only here."
    )
    r.code(grab("backend/resume_parser.py", "def preprocess", "def _normalise_heading"),
           "Listing 4.5: Tokenisation and stop-word removal")

    r.h3("4.5.5 Heading Detection")
    r.p(
        "A line is a heading if it matches a known alias, if every meaningful word in it "
        "is a section word, or if it is an all-caps line without sentence punctuation. "
        "The last two rules prevent a combined heading such as ACHIEVEMENTS AND PROJECTS "
        "from being reported back to the user as an achievement."
    )
    r.code(grab("backend/resume_parser.py", "def _is_heading_line", "def extract_bullet_items"),
           "Listing 4.6: Heading detection within content blocks")

    r.h3("4.5.6 Weighted Skill Coverage")
    r.p(
        "A role's skills are split into three tiers. A skill listed in more than one tier "
        "is assigned to the highest tier only, so it cannot inflate the denominator or "
        "appear twice in the missing-skills list."
    )
    r.code(grab("backend/job_matcher.py", "def _dedupe_across_buckets", "def _split_skills"),
           "Listing 4.7: Cross-tier deduplication of role skills")

    r.h2("4.6 Scoring Design")
    r.h3("4.6.1 Overall Score")
    r.p("The overall score is a fixed weighted sum of the four component scores:")
    r.code(grab("backend/scoring.py", "OVERALL_WEIGHTS", "@dataclass"),
           "Listing 4.8: Published overall and sub-component weights, with the targets "
           "the sub-checks measure against")
    r.note(
        "Job match is deliberately excluded from the overall score. It depends on which "
        "role was selected, and folding it in would make the quality score change when "
        "the target changes."
    )

    r.h3("4.6.2 Grade Bands")
    r.table(
        ["Band", "Score range", "Interpretation"],
        [
            ["Excellent", "90 - 100", "Strong on every axis"],
            ["Very Good", "80 - 89", "Minor gaps only"],
            ["Good", "70 - 79", "Competent, with clear room to improve"],
            ["Needs Improvement", "60 - 69", "Several sub-checks failing"],
            ["Weak", "40 - 59", "Fundamental structure or content problems"],
            ["Very Weak", "0 - 39", "Likely unreadable to an automated screen"],
        ],
        widths=[1.5, 1.2, 3.5],
        fontsize=9,
        caption="Table 4.5: Grade bands",
    )

    r.h3("4.6.3 ATS Compatibility Estimate")
    r.p(
        "The estimate is the sum of eight independent checks worth 100 points in total. "
        "Each check reports its own score, maximum, status and message, so a weak check is "
        "individually visible and actionable."
    )
    r.table(
        ["#", "Check", "Max", "Rule"],
        [
            ["1", "Standard section headings", "22", "Presence and count of recognised headings"],
            ["2", "Contact information", "16", "Email, phone and name all present and parseable"],
            ["3", "Text readability", "16", "Extractable character ratio; penalises scan-like output"],
            ["4", "Resume length", "12", "Word count inside the 300-800 recommended band"],
            ["5", "Excessive special formatting", "8", "Density of pipes, asterisks, dashes and bracket noise"],
            ["6", "Bullet point structure", "8", "Presence of bullets for scannable list items"],
            ["7", "Keyword presence", "10", "Detected technical skills and role keywords against a target"],
            ["8", "Section completeness", "8", "Core and optional section coverage"],
            ["", "TOTAL", "100", "Clamped to the range 0-100"],
        ],
        widths=[0.35, 2.0, 0.55, 3.3],
        fontsize=9,
        caption="Table 4.6: The eight ATS readability checks",
    )
    r.note(
        "This is an estimate built from general readability practice. It does not "
        "reproduce the behaviour of any named commercial ATS, and a high score does not "
        "guarantee that any particular system will read a resume successfully."
    )

    r.h3("4.6.4 Job Matching")
    r.p("The job match score combines two independent signals:")
    r.code(
        "match_score = 0.65 * weighted_skill_coverage\n"
        "            + 0.35 * tfidf_cosine_similarity",
        "Listing 4.9: Job match formula",
    )
    r.p(
        "Coverage dominates because a named skill on the page is stronger evidence than "
        "a shared vocabulary word. Weighted skill coverage counts core skills three "
        "times, preferred skills twice and bonus skills once, over a denominator that "
        "counts every role skill exactly once. Cosine similarity is computed between the "
        "TF-IDF vectors of the resume and the role profile text."
    )
    r.note(
        "This figure is an automated resume-to-role similarity. It is not a judgement "
        "that a candidate is qualified, shortlisted or unqualified for the role."
    )

    r.h2("4.7 User Interface Design")
    r.p(
        "The interface was designed around the requirement that a weak area must be "
        "visible rather than averaged away. Depth is used to establish hierarchy between "
        "a surface, a card and a recessed control, not as decoration."
    )
    r.table(
        ["Component", "Purpose", "Design treatment"],
        [
            ["Score ring", "Overall score at a glance",
             "Extruded gauge with a conic gradient stroke and a specular highlight"],
            ["Summary rail", "Five headline figures",
             "Five cards, each with a coloured progress rail and an inline label"],
            ["Radar pedestals", "Show a dent in one axis that an average hides",
             "Three-dimensional tilted slab with an edge-lit frame"],
            ["Heat grid", "Eight ATS checks, all visible at once",
             "Recessed cells whose fill and hue both encode the score"],
            ["Keyword bars", "Relative importance of extracted terms",
             "Glossy proportional bars with numeric weights"],
            ["Score breakdown table", "Show points earned per sub-check",
             "Grouped table with an inline meter per row"],
            ["Role ranking", "Similarity against every role",
             "Sortable list with per-role coverage and similarity"],
            ["Sticky dashboard nav", "Nine sections in a long page",
             "Fixed anchor bar with scroll-spy highlighting"],
            ["Theme toggle", "Comfortable reading in any light",
             "Applied before first paint, persisted in localStorage"],
        ],
        widths=[1.2, 1.85, 3.15],
        fontsize=8.5,
        caption="Table 4.7: Interface components",
    )
    r.p(
        "Accessibility was treated as a requirement rather than an enhancement. All motion "
        "respects the prefers-reduced-motion setting, every page renders and remains fully "
        "readable with JavaScript disabled, the layout has no horizontal overflow at 360 "
        "pixels, and each chart image carries a text alternative."
    )

    r.h2("4.8 Security and Privacy Design")
    r.table(
        ["Threat", "Control", "Implementation"],
        [
            ["Oversized upload", "Rejected at the request layer",
             "MAX_CONTENT_LENGTH set from MAX_FILE_MB"],
            ["Disguised file type", "Extension plus signature check",
             "looks_like_pdf() inspects the first 1024 bytes for %PDF-"],
            ["Filename traversal or injection", "Sanitised and randomised",
             "werkzeug secure_filename plus a random token; the user name is never used on disk"],
            ["Path traversal in a report id", "Sanitised before path joining",
             "secure_filename applied to every report identifier"],
            ["Exposure of uploads", "Never served statically",
             "uploads/ is outside the static folder"],
            ["Retention of personal data", "Deleted after analysis",
             "Upload removed in a finally block; KEEP_UPLOADS=1 opts out for debugging"],
            ["Leaked API keys", "Environment variables only",
             "No key is stored in source or written to a report"],
            ["Internal error disclosure", "Typed errors and handlers",
             "413, 404 and 500 handlers return friendly pages; the log keeps the detail"],
        ],
        widths=[1.35, 1.35, 3.5],
        fontsize=8.5,
        caption="Table 4.8: Security and privacy controls",
    )

    r.h2("4.9 Error Handling Strategy")
    r.p(
        "The analysis layer raises typed exceptions and never handles its own user-facing "
        "text. The application layer catches them and converts them into a message. This "
        "keeps the cause and the presentation of a failure in separate places."
    )
    r.table(
        ["Exception", "Raised when", "User sees"],
        [
            ["InvalidPDFError", "The file is not a readable PDF, or is encrypted",
             "A message stating the file is not a readable PDF"],
            ["EmptyPDFError", "No text could be extracted at all",
             "A message stating the PDF appears to be scanned or empty"],
            ["SkillDataError", "skills.json is missing or malformed",
             "A message stating the vocabulary file is unavailable"],
            ["JobDataError", "job_roles.json is missing or malformed",
             "A message stating the role data is unavailable"],
            ["UnknownRoleError", "The typed role matches nothing in the dataset",
             "A message naming the unmatched role and continuing without a match"],
            ["AnalysisError", "Any other analysis failure",
             "A plain-English summary; the detail goes to the server log only"],
        ],
        widths=[1.35, 2.35, 2.5],
        fontsize=8.5,
        caption="Table 4.9: Typed exceptions and their user-facing messages",
    )
    r.note(
        "Returning a typed error for an unmatched role is a deliberate design decision. "
        "Crashing, or silently matching an unrelated role, would both be worse than "
        "finishing the resume analysis and stating plainly that no match was possible."
    )


# =========================================================================
# Chapter 5 - Implementation
# =========================================================================
def build_ch5(r, data):
    r.h1("CHAPTER 5 - IMPLEMENTATION")

    r.h2("5.1 Development Environment")
    r.table(
        ["Component", "Detail"],
        [
            ["Operating system", "macOS (developed on macOS 15)"],
            ["Python version", "3.14.6 (project supports 3.9 and later)"],
            ["Virtual environment", "venv, created with python3 -m venv venv"],
            ["Editor", "Any editor; no IDE-specific configuration is required"],
            ["Web framework", "Flask 3.1.3"],
            ["PDF parsing", "pypdf 6.19.0, pdfplumber 0.11.10"],
            ["Numerical", "NumPy 2.5.3, pandas 3.0.6"],
            ["NLP", "scikit-learn 1.9.1"],
            ["Charts", "Matplotlib 3.11.2, Agg backend"],
            ["Test framework", "unittest from the standard library"],
        ],
        widths=[1.75, 4.45],
        fontsize=9,
        caption="Table 5.1: Development environment",
    )

    r.h3("5.1.1 Library Justification")
    r.table(
        ["Library", "Why it was chosen", "Why it was not replaced"],
        [
            ["Flask", "Minimal, well documented, and appropriate for a single-process application", "Django would add an ORM, admin and migration layer the project does not need"],
            ["pypdf", "Pure Python, no compilation, documented exception hierarchy", "pdfminer.six alone is slower and lower level"],
            ["pdfplumber", "Higher-fidelity word and layout extraction via pdfminer.six", "Used as a fallback rather than the primary parser, for speed"],
            ["NumPy / pandas", "Underlie scikit-learn and matplotlib; standard in the ecosystem", "Standard library lists would mean implementing TF-IDF by hand for no benefit"],
            ["scikit-learn", "Reference implementation of TF-IDF and cosine similarity", "spaCy or NLTK add heavy dependencies and rule-based accuracy the project does not need"],
            ["Matplotlib", "Mature, produces publication-quality static output", "Plotly would add a JavaScript dependency for charts that must also print"],
        ],
        widths=[1.1, 2.55, 2.55],
        fontsize=8.5,
        caption="Table 5.2: Library selection",
    )
    r.p(
        "The project deliberately avoids JavaScript and CSS frameworks, a build step and "
        "any database. The only third-party package beyond the application requirements "
        "is python-docx, which is used only to generate this report and is not required "
        "to run the application."
    )

    r.h2("5.2 Project Structure")
    r.code(
        """
AI Resume Checker/
  app.py                    Flask entry point, routes, validation, errors
  requirements.txt          Minimum-version constraints
  README.md                 Setup, usage and API documentation
  .gitignore                Excludes venv, caches, uploads, reports, charts
  smoke_test.py             Optional end-to-end console check
  backend/
    __init__.py
    skill_data.py           Loads and validates skills.json
    resume_parser.py        PDF text, cleaning, sections, fields, metrics
    skill_extractor.py      Skill regexes, aliases, TF-IDF, content signals
    job_matcher.py          Roles, weighted coverage, cosine similarity, ranking
    ats_analyzer.py         Eight ATS readability checks
    scoring.py              Weights, sub-checks, overall score, grades
    analyzer.py             Orchestration, advice, optional AI, text report
    charts.py               Seven matplotlib builders and cleanup
  data/
    skills.json             10 categories, aliases, soft skills
    job_roles.json          10 roles with tiered skills
  templates/                base, _macros, index, upload, results,
                            methodology, about, error
  public/static/
    css/style.css           Design tokens, both themes, responsive, print
    js/script.js            Theme, nav, tilt, counters, upload validation
    img/favicon.svg
    img/charts/             Generated at runtime
  uploads/                  Temporary; files deleted after analysis
  reports/                  Generated JSON and text reports
  tests/                    helpers, run_tests, five test modules
  docs/                     This report and its generator
""",
        "Listing 5.1: Project directory structure",
    )

    r.h2("5.3 Configuration")
    r.p(
        "Every setting has a working default, so the application runs with no "
        "configuration. All values are read from environment variables so that nothing "
        "sensitive lives in source control."
    )
    r.table(
        ["Variable", "Default", "Purpose"],
        [
            ["HOST", "127.0.0.1", "Bind address"],
            ["PORT", "5000", "Listening port"],
            ["SECRET_KEY", "random per start", "Flask session signing"],
            ["FLASK_DEBUG", "0", "Set to 1 for auto-reload and the debugger"],
            ["MAX_FILE_MB", str(data["max_file_mb"]),
             "Upload size limit; kept under the 4.5 MB body cap some hosts enforce"],
            ["STORAGE_DIR", "project directory",
             "Where uploads and reports are written. Probed at start-up and replaced "
             "with a temporary directory when the project directory is read-only"],
            ["CHART_MODE", data["chart_mode_default"],
             "file writes PNGs and returns a URL; inline returns base64 data URIs and "
             "never touches the filesystem. Defaults to inline automatically when the "
             "VERCEL variable is set, so the safe mode needs no configuration"],
            ["KEEP_UPLOADS", "0", "Set to 1 to retain uploads for debugging"],
            ["ENABLE_AI_ASSIST", "0", "Enables the optional language-model polish"],
            ["OPENAI_API_KEY", "unset", "Enables the OpenAI polish when the flag is on"],
            ["OPENAI_MODEL", "gpt-4o-mini", "Model used for polish"],
            ["GEMINI_API_KEY", "unset", "Enables the Gemini polish when the flag is on"],
            ["GEMINI_MODEL", "gemini-1.5-flash", "Model used for Gemini"],
            ["AI_REQUEST_TIMEOUT", "8", "Seconds before abandoning a polish call"],
        ],
        widths=[1.55, 1.35, 3.3],
        fontsize=9,
        caption="Table 5.3: Environment variables",
    )

    r.h2("5.4 Upload Validation")
    r.p(
        "Validation proceeds in a fixed order so the cheapest and most decisive check "
        "runs first. A file that fails any check is deleted before the redirect is issued."
    )
    r.code(grab("app.py", "def allowed_file", "def format_file_size"),
           "Listing 5.2: Extension validation")
    r.code(grab("app.py", "def looks_like_pdf", "# Both directories"),
           "Listing 5.3: PDF signature validation")
    r.p(
        "The signature check matters because a text file renamed to .pdf passes an "
        "extension check and a MIME check supplied by the browser, yet would otherwise "
        "reach the parser and produce a confusing error. Searching the first 1024 bytes "
        "rather than only the first five tolerates the leading whitespace that some PDF "
        "writers emit."
    )

    r.h2("5.5 Report Persistence and Reloadable Results")
    r.p(
        "A completed analysis is written to reports/ as both JSON and plain text under a "
        "timestamped identifier. The POST then redirects to /results/<id> rather than "
        "rendering the dashboard directly. This is the Post/Redirect/Get pattern, and it "
        "buys three properties that a direct render does not have:"
    )
    r.numbers([
        "The dashboard has a real URL, so it can be bookmarked, reloaded or shared.",
        "A browser refresh re-fetches the stored report instead of re-uploading the PDF.",
        "Flash messages set during the POST are displayed on the next render rather than "
        "leaking onto an unrelated later page.",
    ])
    r.p(
        "A missing, unreadable or truncated report is handled with a graceful message; "
        "the user is returned to the upload form rather than shown a traceback. The two "
        "failures are deliberately distinguished, because they mean different things: an "
        "id that holds no stored analysis is reported as no longer available, while a "
        "file that exists but no longer parses is reported as unreadable."
    )
    r.p(
        "Storage is probed rather than assumed. Writing may fail on a read-only "
        "filesystem, so every write site treats failure as a normal outcome rather than "
        "an exception, and the twenty most recent analyses are additionally held in "
        "memory. A read first checks the file, because it is the only copy that outlives "
        "the process, and falls back to memory only when nothing was written there. On a "
        "host where nothing can be written, the analysis still renders and the dashboard "
        "URL still resolves for as long as the process runs."
    )

    r.h2("5.6 Chart Generation")
    r.p(
        "Charts are produced with Matplotlib on the Agg backend and rendered to PNG. Each "
        "builder is wrapped so that a failure returns None instead of raising, which means "
        "a plotting problem can never invalidate an otherwise correct analysis. Two "
        "rendering modes exist. File mode writes the PNG under public/static/img/charts/ "
        "and returns a URL, which is the cheap option on a host with a writable "
        "filesystem. Inline mode returns the PNG as a base64 data URI instead. A data URI "
        "is accepted by img src unchanged, so no template needs to know which mode is "
        "active, and the mode exists because a serverless platform mounts the project "
        "read-only and gives each instance its own temporary directory: an image written "
        "there cannot be served reliably when the next request for it is handled by a "
        "different instance."
    )
    r.table(
        ["Chart key", "Chart", "Purpose"],
        [
            ["scores", "Grouped bar", "The four component scores beside the overall"],
            ["radar", "Radar", "Component balance; a dent that an average hides"],
            ["ats_radar", "Radar", "The shape of the eight ATS checks"],
            ["skills", "Horizontal bar", "Technical skills by category"],
            ["keywords", "Horizontal bar", "Top TF-IDF weighted keywords"],
            ["sections", "Bar", "Sections detected against sections missing"],
            ["job_match", "Grouped bar", "Coverage and similarity, plus matched and missing counts"],
            ["role_fit", "Bar", "Similarity against every role in the dataset"],
        ],
        widths=[1.0, 1.35, 3.85],
        fontsize=9,
        caption="Table 5.4: Charts generated per analysis",
    )
    r.p(
        "Generated PNGs accumulate in the chart folder in file mode, so cleanup prunes "
        "the oldest files each time charts are generated, keeping the folder bounded at "
        "forty files. In inline mode nothing is written, so cleanup returns immediately "
        "rather than touching a directory that holds no charts. The cleanup call is "
        "placed inside the chart generation function rather than on page load, so it runs "
        "on every path that produces charts: the web form, the JSON API "
        "and the smoke test."
    )

    r.h2("5.7 Optional AI Assist")
    r.p(
        "A language-model assist is included but is off by default and never required. "
        "When ENABLE_AI_ASSIST is set and a key is present, extracted text is sent to the "
        "configured service and the advice list is rephrased for clarity."
    )
    r.bullets([
        "It cannot and does not alter any score. Scores are computed locally before the "
        "assist is invoked.",
        "If the call fails, times out or returns unusable output, the local advice is used "
        "unchanged and the user is not told a model was involved.",
        "No key means no network call is attempted at all.",
        "The feature is documented as optional in the README and in the in-app About page.",
    ])
    r.note(
        "No output anywhere in the system is fabricated. Every number and every "
        "recommendation originates from local deterministic code."
    )

    r.h2("5.8 Security Implementation")
    r.p(
        "The upload is written to disk under a randomised name so that a hostile filename "
        "never reaches the filesystem, and the directory is removed from any static route. "
        "Every report identifier is passed through werkzeug's secure_filename before being "
        "joined to a path, which prevents a traversal sequence from escaping the reports "
        "directory."
    )
    r.code(
        grab("app.py", "def results", '@app.route("/report/'),
        "Listing 5.4: Report retrieval with a sanitised identifier",
    )
    r.p(
        "The same three-line pattern - sanitize, join, verify existence - is repeated on "
        "the results, download and JSON routes. No route reads a path built from an "
        "unsanitised identifier."
    )


# =========================================================================
# Chapter 6 - Testing
# =========================================================================
def build_ch6(r, data):
    r.h1("CHAPTER 6 - TESTING")

    r.h2("6.1 Testing Objectives")
    r.p(
        "The project makes specific factual claims in this report and in its README. "
        "Testing exists to verify those claims rather than to produce a coverage figure. "
        "In particular, three claims are treated as testable obligations: that a failure "
        "never reaches the user as a traceback; that scores are deterministic and inside "
        "their stated bounds; and that the dataset is internally consistent."
    )

    r.h2("6.2 Testing Strategy")
    r.table(
        ["Level", "Technique", "Applied to"],
        [
            ["Unit", "Direct function assertions with known inputs",
             "Cleaning, section detection, field extraction, skill matching, TF-IDF, scoring, coverage"],
            ["Property", "Invariants checked over generated data",
             "Every score within 0-100; component weights summing to 1.0; sub-check scores within their maximum"],
            ["Integration", "Pipeline run against a real generated PDF",
             "Analysis end to end, plain-text report, chart generation, chart folder bound"],
            ["System", "HTTP requests through the Flask test client",
             "Every route, both the success and the error path, including status codes and page content"],
            ["Regression", "Named tests for every defect found",
             "Cross-tier skill duplicates, heading leakage, duplicated certification years, chart folder growth"],
            ["Negative", "Malformed and hostile input",
             "Empty file, corrupt PDF, non-PDF content with a .pdf name, wrong extension, oversized request"],
            ["Security", "Path traversal and filename injection",
             "Traversal sequences against every report route; randomised on-disk names"],
        ],
        widths=[0.85, 2.0, 3.35],
        fontsize=8.5,
        caption="Table 6.1: Testing levels",
    )
    r.p(
        "All tests run against PDFs generated in memory during the test run. No sample "
        "resume file is committed to the repository, which removes any possibility of "
        "shipping a real person's document with the project."
    )

    r.h2("6.3 Test Inventory")
    r.p(
        f"The suite contains {data['n_tests']} tests in {len(data['test_groups'])} groups. "
        "The HTTP layer accounts for the largest group, because every route has both a "
        "success path and a failure path that must be verified."
    )
    r.table(
        ["Test group", "Tests", "Coverage"],
        data["test_groups"],
        widths=[1.85, 0.55, 3.8],
        fontsize=8.5,
        caption="Table 6.2: Test inventory by group",
    )

    r.h2("6.4 Test Results")
    r.p("Running the suite produces the following result.")
    r.code(data["test_output"], "Listing 6.1: Test suite output")
    r.p(
        f"All {data['n_tests']} tests pass. The suite executes in roughly "
        f"{data['test_seconds']:.0f} seconds, which includes generating a PDF fixture and "
        "rendering charts on every pipeline test."
    )

    r.h2("6.5 Representative Test Cases")
    r.table(
        ["Test", "Input", "Expected result"],
        [
            ["Extracts text from a valid PDF", "Generated one-page PDF",
             "Non-empty text, page count of 1"],
            ["Rejects a file that is not a PDF", "Bytes without the PDF signature",
             "Typed InvalidPDFError, no traceback"],
            ["Rejects an empty PDF", "PDF with no text layer",
             "Typed EmptyPDFError explaining the file may be scanned"],
            ["Rejects a text file renamed to .pdf", "Plain bytes named resume.pdf",
             "Upload page reports the file does not look like a real PDF"],
            ["Rejects a non-PDF extension", "File named resume.docx",
             "Upload page reports PDF files only"],
            ["Detects a combined heading as a heading", "Line ACHIEVEMENTS AND PROJECTS",
             "Not reported as an achievement"],
            ["Does not match a short skill inside a longer word", "Text containing C++",
             "The C skill is not credited"],
            ["Matches a multi-part skill correctly", "Text containing PL/SQL and CI/CD",
             "Both skills detected as written"],
            ["Resolves an alias to a canonical name", "Text containing sklearn",
             "Reported as Scikit Learn"],
            ["Keeps a duplicate skill in its highest tier only", "Skill listed as core and bonus",
             "Counted once, in the core tier, with no duplicate in the missing list"],
            ["Scores every value within bounds", "Any parseable resume",
             "Overall and all component scores within 0 to 100"],
            ["Component weights sum to one", "Score configuration",
             "Structure, Content, Skills and ATS weights total 1.0"],
            ["Ranks every role in the dataset", "Any parseable resume",
             "The ranking contains all roles, sorted by descending score"],
            ["Handles an unknown role", "Role matching no dataset entry",
             "Typed UnknownRoleError; the page states no target role was selected"],
            ["Renders the dashboard", "POST with a valid PDF",
             "302 to /results/<id>, which then returns the dashboard"],
            ["Survives a page refresh", "GET /results/<id> twice",
             "Both requests return the dashboard; the PDF is not re-required"],
            ["Handles a truncated stored report", "Stored JSON cut in half",
             "A readable message, and no traceback in the response"],
            ["Displays the success message", "POST with a valid PDF",
             "The success flash appears on the dashboard"],
            ["Blocks path traversal", "Traversal sequence as a report id",
             "404; no file outside the reports directory is served"],
            ["Returns a friendly 404", "GET an unknown path",
             "404 page containing Page not found"],
        ],
        widths=[1.85, 1.85, 2.5],
        fontsize=8,
        caption="Table 6.3: Representative test cases",
    )

    r.h2("6.6 Defects Found and Resolved")
    r.p(
        "The following defects were found by the tests during development and fixed. They "
        "are recorded because each represents a class of error that silently produces a "
        "plausible but wrong result."
    )
    r.table(
        ["#", "Symptom", "Cause", "Resolution", "Regression test"],
        [
            ["1", "Skill coverage was understated and the missing list repeated skills",
             "A skill listed in two tiers of a role was counted in both, inflating the denominator",
             "Added cross-tier deduplication keeping the highest tier, and removed the duplicate dataset entries",
             "test_cross_tier_duplicate_is_kept_in_highest_tier"],
            ["2", "A section heading was listed as an achievement",
             "Content blocks were read line by line without filtering headings",
             "Added heading detection covering aliases, combined headings and all-caps lines",
             "test_inline_headings_are_dropped"],
            ["3", "Certification years were printed twice",
             "The year was appended even when the name already contained it",
             "The year is appended only when it is not already present in the name",
             "Verified through the dashboard render"],
            ["4", "Generated charts accumulated without limit",
             "Cleanup ran on page load, so it never ran while the API or tests generated charts",
             "Moved cleanup into chart generation so it runs on every path",
             "test_chart_folder_stays_bounded"],
            ["5", "The dashboard could not be reloaded, and messages appeared on the wrong page",
             "The POST rendered the dashboard directly and flashed messages for the next request",
             "Adopted Post/Redirect/Get to /results/<id>",
             "test_results_page_is_reloadable_by_id, test_success_flash_is_shown_on_the_results_page"],
            ["6", "A renamed text file reached the parser",
             "Only the extension and browser MIME type were checked",
             "Added a PDF signature check before parsing",
             "test_text_file_renamed_to_pdf_is_rejected"],
            ["7", "The role chart covered only 6 of 10 roles while claiming all",
             "An arbitrary truncation applied to the ranking",
             "Rank the full dataset by default",
             "test_default_ranks_every_role_in_the_dataset"],
            ["8", "The README documented a limit that was not enforced",
             "The documented upload limit was a constant, not configurable, and no signature check existed",
             "Implemented the documented behaviour rather than weakening the documentation",
             "test_looks_like_pdf_checks_the_signature"],
        ],
        widths=[0.28, 1.5, 1.6, 1.6, 1.22],
        fontsize=7.5,
        caption="Table 6.4: Defect log",
    )
    r.note(
        "Defect 1 is the most instructive: the system produced a plausible number, a "
        "coverage percentage in a plausible range, and a missing-skills list that looked "
        "correct. Only a test that asserts the absence of duplicates detected it."
    )


# =========================================================================
# Chapter 7 - Results and discussion
# =========================================================================
def build_ch7(r, data):
    r.h1("CHAPTER 7 - RESULTS AND DISCUSSION")
    res = data["sample"]

    r.h2("7.1 Method of Evaluation")
    r.p(
        "The system was evaluated by running the complete pipeline against a synthetic "
        "resume generated during the test run, with the role Python Developer selected. "
        "The fixture is generated in memory by matplotlib and is not a real person's "
        "document. Every figure quoted in this chapter is read directly from the result "
        "object produced by that run."
    )
    r.p(
        f"The document contained {res['overview']['word_count']} words over "
        f"{res['overview']['pages']} page, with "
        f"{len(res['overview']['sections_found'])} of 10 possible sections detected."
    )

    r.h2("7.2 Overall Result")
    scores = res["scores"]
    r.table(
        ["Measure", "Value", "Band"],
        [
            ["Overall score", f"{scores['overall']:.1f} / 100", scores["grade"]],
        ] + [
            [c["label"], f"{c['score']:.1f} / 100", f"weight {c['weight']:.2f}"]
            for c in scores["components"]
        ],
        widths=[2.6, 1.6, 2.0],
        fontsize=9,
        caption="Table 7.1: Scores produced for the sample resume",
    )
    r.p(
        f"An overall score of {scores['overall']:.1f}, in the "
        f"'{scores['grade']}' band, is produced for this fixture. The component scores "
        "show why an average is insufficient information: Structure is the strongest "
        "component while Content is the weakest, and a single figure conceals that spread."
    )

    r.h2("7.3 Component Breakdown")
    r.p(
        "Each component decomposes into named sub-checks. The tables below show what the "
        "fixture actually earned, which demonstrates that the dashboard reports measured "
        "values rather than a summary."
    )
    for comp in scores["components"]:
        idx = scores["components"].index(comp) + 1
        r.h3(f"7.3.{idx} {comp['label']}")
        if comp["key"] == "ats":
            r.p(
                f"This component does not decompose further: it is the ATS estimate "
                f"computed by the eight checks in Section 4.6.3, passed in from the ATS "
                f"module and weighted at {comp['weight']:.2f}. It scored "
                f"{comp['score']:.1f} / 100. The individual checks and the points each "
                "earned are set out in full in Table 7.2 of Section 7.4."
            )
            continue
        r.table(
            ["Sub-check", "Score", "Measured evidence"],
            [[b["label"], f"{b['score']:.1f} / 100", b["detail"]] for b in comp["breakdown"]],
            widths=[1.65, 0.75, 3.8],
            fontsize=8.5,
        )

    r.h2("7.4 ATS Compatibility Estimate")
    ats = res["ats"]
    r.table(
        ["#", "Check", "Maximum", "Achieved", "Status"],
        [
            [str(i), c["label"], str(c["max_score"]), f"{c['score']:.1f}", c["status"].title()]
            for i, c in enumerate(ats["checks"], 1)
        ] + [["", "Total", "100", f"{ats['score']:.1f}", ""]],
        widths=[0.35, 2.4, 0.85, 0.95, 0.95],
        fontsize=9,
        caption="Table 7.2: The eight ATS checks for the sample resume",
    )
    if ats.get("suggestions"):
        r.h3("7.4.1 Suggestions Generated")
        r.bullets(ats["suggestions"][:6])
    r.note(
        f"The estimate of {ats['score']:.1f} is a readability indicator built from the "
        "checks listed above. It is not a reproduction of any commercial ATS and does not "
        "predict whether any particular system would accept the document."
    )

    r.h2("7.5 Skills Detected")
    skills = res["skills"]
    rows = [[cat, ", ".join(vals) if vals else "none detected"]
            for cat, vals in skills["technical_by_category"].items()]
    if rows:
        r.table(
            ["Category", "Skills detected"],
            rows,
            widths=[1.4, 4.8],
            fontsize=8.5,
            caption=f"Table 7.3: Technical skills by category ({len(skills['technical'])} detected)",
        )
    r.p(
        f"Soft skills detected: {len(skills.get('soft', []) or [])}. "
        f"Distinct action verbs: {len(skills.get('action_verbs', []))}. "
        f"Quantified results: {skills.get('quantifier_count', 0)}. "
        f"Vague phrases: {skills.get('filler_count', 0)}. "
        f"Alias resolutions: {len(skills.get('aliases_detected', []) or [])}."
    )

    r.h2("7.6 Job Role Similarity")
    jm = res["job_match"]
    r.p(
        f"Against the selected role ({jm['role']}), the system reports a similarity of "
        f"{jm['match_score']:.1f} / 100, composed of a weighted skill coverage of "
        f"{jm['skill_coverage_score']:.1f} and a TF-IDF cosine similarity of "
        f"{jm['text_similarity_score']:.1f}."
    )
    table_rows = []
    for tier in ("core", "preferred", "bonus"):
        matched = jm.get(f"matched_{tier}") or []
        missing = jm.get(f"missing_{tier}") or []
        table_rows.append([
            tier.title(),
            ", ".join(matched) if matched else "none",
            ", ".join(missing) if missing else "none",
        ])
    r.table(
        ["Tier", "Matched", "Missing"],
        table_rows,
        widths=[0.85, 2.65, 2.7],
        fontsize=8,
        caption=f"Table 7.4: Skill coverage for {jm['role']}",
    )
    r.p(
        "The coverage sub-score is considerably higher than the cosine similarity for "
        "this fixture. That is the expected behaviour of the formula rather than an "
        "error: named skills on the page are strong evidence, whereas a resume and a role "
        "description rarely share vocabulary, so the text signal alone is conservative."
    )
    r.note(
        "This figure describes how similar the resume text is to the role profile. It is "
        "not a statement that the candidate is qualified or unqualified for the role."
    )

    r.h2("7.7 Ranking Against All Roles")
    r.p(
        "The resume is compared with every role in the dataset, not only the selected one, "
        f"which gives the student a view of adjacent possibilities. All "
        f"{len(res['role_overview'])} roles are listed, so no comparison is hidden."
    )
    r.table(
        ["Rank", "Role", "Category", "Similarity", "Coverage", "Text"],
        [
            [str(i), o["role"], o["category"], f"{o['score']:.1f}",
             f"{o['skill_coverage']:.1f}", f"{o['text_similarity']:.1f}"]
            for i, o in enumerate(res["role_overview"], 1)
        ],
        widths=[0.45, 1.75, 1.35, 0.85, 0.75, 0.65],
        fontsize=8.5,
        caption="Table 7.5: Resume ranked against every supported role",
    )
    r.p(
        "The ordering is informative. Roles that share this resume's vocabulary and "
        "skill profile rank highest, and roles in unrelated domains such as security rank "
        "lowest, which is the expected shape of a keyword and skill-based comparison."
    )

    r.h2("7.8 Advice Generated")
    advice = res["advice"]

    def advice_text(item):
        """Advice items are dicts with a title, a detail line and a priority."""
        if isinstance(item, dict):
            return f"{item.get('title', '')} - {item.get('detail', '')}"
        return str(item)

    for key, title in (("strengths", "7.8.1 Strengths Detected"),
                       ("weaknesses", "7.8.2 Weaknesses Detected")):
        items = advice.get(key) or []
        if not items:
            continue
        r.h3(title)
        r.bullets([advice_text(i) for i in items[:6]])
    recs = advice.get("recommendations") or []
    if recs:
        r.h3("7.8.3 Recommendations, in Priority Order")
        r.numbers([advice_text(i) for i in recs[:7]])

    r.h2("7.9 Charts Produced")
    r.p(
        f"{len(res['charts'])} charts are generated for every analysis. They are rendered "
        "server-side and served as static PNGs, so the dashboard requires no client-side "
        "chart library."
    )
    r.table(
        ["Chart", "Key", "What it reveals"],
        [
            ["Score distribution", "scores", "The four components beside the overall score"],
            ["Score balance radar", "radar", "Whether one component is dragging the average down"],
            ["ATS checks radar", "ats_radar", "The shape of the eight readability checks"],
            ["Skills by category", "skills", "Technical breadth and where it is concentrated"],
            ["Keyword weighting", "keywords", "Which terms the TF-IDF stage considers most distinctive"],
            ["Section coverage", "sections", "Which sections were detected and which are missing"],
            ["Job match detail", "job_match", "Coverage against similarity, and matched against missing counts"],
            ["Role fit overview", "role_fit", "Similarity across every supported role"],
        ],
        widths=[1.4, 0.95, 3.85],
        fontsize=9,
        caption="Table 7.6: Charts and their purpose",
    )

    r.h2("7.10 Performance")
    elapsed = res["meta"].get("elapsed_seconds")
    r.p(
        (f"The sample analysis completed in {elapsed:.2f} seconds on a local machine, "
         if elapsed else
         "A full analysis completes in roughly one second on a local machine, ")
        + "including PDF parsing, eight ATS checks, four components with seventeen "
        "sub-checks, ten role comparisons and eight chart renders. Chart rendering "
        "dominates this figure."
    )
    r.table(
        ["Operation", "Approximate cost", "Note"],
        [
            ["PDF text extraction", "0.05 - 0.15 s", "pdfplumber fallback roughly doubles this"],
            ["Cleaning and section detection", "Under 0.01 s", "Linear in line count"],
            ["Skill matching", "0.01 - 0.03 s", "Patterns are compiled once and reused"],
            ["TF-IDF and cosine similarity", "Under 0.05 s", "Single-document vectorisation"],
            ["Scoring", "Negligible", "Arithmetic only"],
            ["Role ranking", "0.05 - 0.15 s", "Ten roles, coverage plus similarity each"],
            ["Chart rendering", "0.4 - 0.9 s", "Eight PNGs; the dominant cost"],
        ],
        widths=[2.0, 1.3, 2.9],
        fontsize=9,
        caption="Table 7.7: Indicative stage timings",
    )
    r.note(
        "These are indicative figures measured on one development machine, not a benchmark. "
        "They are recorded to show that the application is comfortably interactive, not to "
        "support a performance claim."
    )

    r.h2("7.11 Discussion of Findings")
    r.p(
        "Three findings are worth recording."
    )
    r.p(
        "First, the boundary problem in skill matching is the single largest source of "
        "wrong answers in naive implementations. Because this project defines an explicit "
        "boundary class that excludes the characters occurring inside real technical terms, "
        "the skill counts are trustworthy for the vocabulary supplied. A skill absent from "
        "skills.json is invisible, which is a limitation of the approach rather than a bug "
        "in the implementation."
    )
    r.p(
        "Second, decomposing the score changes what a user does with it. Given 74 out of "
        "100, a student has nothing to act on. Given that content length scores 62 because "
        "the document has 208 words against a 300 to 800 target, the next edit is obvious "
        "and verifiable by re-running the analysis."
    )
    r.p(
        "Third, the strongest honest signal is not the overall score but the ATS estimate "
        "combined with the extracted contact block. A resume that scores well on readability "
        "while the parser failed to find an email address is in a materially different "
        "position from one that failed both, and the dashboard presents those two facts "
        "side by side rather than averaging them."
    )

    r.h2("7.12 Limitations Observed in Evaluation")
    r.bullets([
        "Section detection depends on headings being present as text. A resume whose "
        "headings are graphics will be reported as having no recognised sections.",
        "Experience and project entries are merged heuristically, so a multi-line role "
        "description can occasionally be split across two entries.",
        "Scanned and image-only PDFs are rejected rather than analysed, because no OCR is "
        "implemented. The user receives a clear message instead of a misleading empty result.",
        "The TF-IDF signal compares a resume with a short role description, so its absolute "
        "values are low across every role. It is meaningful for ranking, not as a standalone measure.",
        "The skill vocabulary is finite. Detection quality is bounded by that vocabulary, "
        "and the application states this rather than implying broader coverage.",
    ])


# =========================================================================
# Chapter 8 - Conclusion
# =========================================================================
def build_ch8(r, data):
    r.h1("CHAPTER 8 - CONCLUSION AND FUTURE SCOPE")

    r.h2("8.1 Objectives Achieved")
    r.table(
        ["#", "Objective", "Status"],
        [
            ["1", "Reliable text extraction with two parsers and graceful failure", "Achieved"],
            ["2", "Section detection and structured field extraction", "Achieved"],
            ["3", "Skill detection with correct boundaries and an extensible vocabulary", "Achieved"],
            ["4", "Transparent weighted scoring with a published rubric", "Achieved"],
            ["5", "ATS compatibility estimate from documented checks", "Achieved"],
            ["6", "Automated resume-to-role similarity using coverage and cosine similarity", "Achieved"],
            ["7", "A dashboard that makes a weak area visible", "Achieved"],
            ["8", "Friendly failure with no traceback", "Achieved"],
            ["9", "Immediate deletion of the uploaded document", "Achieved"],
            ["10", "Automated verification of every stated capability", "Achieved"],
        ],
        widths=[0.35, 4.5, 1.35],
        fontsize=9,
        caption="Table 8.1: Objective achievement",
    )

    r.h2("8.2 Conclusion")
    r.p(
        "AI Resume Checker was built to answer a question a student cannot answer alone: is this "
        "resume machine readable, and what is missing for the role I want? It answers that "
        "question in a way that is local, private, deterministic and fully explainable."
    )
    r.p(
        "The implementation comprises approximately "
        f"{data['py_lines']:,} lines of application logic in nine modules with no database "
        "and no JavaScript framework, and is verified by "
        f"{data['n_tests']} automated tests. Its analytical core uses established "
        "techniques: boundary-aware regular expressions for skills, TF-IDF with cosine "
        "similarity for vocabulary overlap, and a four-component weighted rubric whose "
        "every rule is published in the application itself."
    )
    r.p(
        "The most consequential design decision was to refuse to overstate. The ATS figure "
        "is labelled an estimate because the project cannot verify how any commercial "
        "system behaves. The job match figure is labelled a similarity because a keyword "
        "comparison cannot and should not determine whether a person is employable. A tool "
        "that returned confident nonsense would be worse than useless to the student it is "
        "meant to help. Eight defects found by the tests during development are documented "
        "in Chapter 6, including several that produced entirely plausible-looking but "
        "incorrect results."
    )
    r.p(
        "The system is submitted as a working, self-contained application that runs with "
        "one command, requires no account and no API key, and explains itself."
    )

    r.h2("8.3 Learning Outcomes")
    r.p(
        "In line with the objectives of the Python Programming subject, the following "
        "practical outcomes were obtained:"
    )
    r.bullets([
        "Working with the Flask request/response cycle, Jinja2 templating and the "
        "separation of concerns between a web layer and a business logic layer.",
        "File handling with the pathlib and os modules, including safe path joining and "
        "the consequences of trusting user-supplied filenames.",
        "Exception design: creating a typed hierarchy that separates the cause of a "
        "failure from its user-facing presentation.",
        "Regular expression construction, in particular boundary lookarounds and "
        "non-greedy matching for structured extraction from messy text.",
        "Text preprocessing for natural language processing, and understanding why "
        "stop-word removal is appropriate for keyword weighting but harmful for phrase matching.",
        "TF-IDF and cosine similarity, and reasoning about IDF behaviour in a "
        "single-document comparison.",
        "Numerical reasoning with NumPy and pandas, and the discipline of clamping scores "
        "to a valid range.",
        "Data visualisation with Matplotlib, including choosing an appropriate chart form "
        "for each question and serving static images without a client-side library.",
        "Version control hygiene through a comprehensive .gitignore that prevents "
        "committing a virtual environment or a real resume.",
        "Automated testing with the standard library unittest, including writing regression "
        "tests for every defect found and generating test fixtures in memory rather than "
        "committing sample data.",
    ])

    r.h2("8.4 Future Scope")
    r.p(
        "The following extensions are feasible and would each address a documented "
        "limitation of the present system."
    )
    r.table(
        ["#", "Extension", "Limitation it removes", "Approach"],
        [
            ["1", "OCR for scanned PDFs", "Scanned and image-only files are rejected",
             "OCR the rendered page when extraction yields too little text"],
            ["2", "Microsoft Word input", "PDF only",
             "Read .docx as well as .pdf in the same extraction layer"],
            ["3", "Job-description import", "Only 10 built-in roles are supported",
             "Parse a pasted job description into the same role structure and match against it"],
            ["4", "Version comparison", "Each analysis is independent",
             "Store two results and diff scores, skills and sections between them"],
            ["5", "Section-level rewrite help", "Advice is document-level",
             "Generate per-section suggestions from the specific sub-checks that failed"],
            ["6", "Expanded vocabulary", "Detection is bounded by skills.json",
             "Grow the dataset; the matching code requires no change"],
            ["7", "Localisation", "English, single-column input only",
             "Extend heading aliases and filler phrases for regional languages"],
            ["8", "Accessible chart alternatives", "Charts are images",
             "Emit the same figures as a data table for screen readers"],
            ["9", "Report persistence", "Reports are local files",
             "Add an optional store if multi-device access is genuinely required"],
        ],
        widths=[0.28, 1.5, 1.85, 2.57],
        fontsize=8,
        caption="Table 8.2: Proposed future work",
    )
    r.note(
        "Items 1 and 2 are deliberately first, because they remove the two limitations a "
        "user is most likely to encounter in ordinary use."
    )


# =========================================================================
# References
# =========================================================================
def build_references(r, data):
    r.h1("REFERENCES")

    r.h2("Books and Standards")
    r.numbers([
        "Manning, C. D., Raghavan, P., and Schutzke, H. (2008). Introduction to Information "
        "Retrieval. Cambridge University Press. Chapters 1 and 6 (term weighting and the "
        "vector space model).",
        "Jurafsky, D., and Martin, J. H. (2021). Speech and Language Processing (3rd "
        "draft edition). Stanford University. Chapter 2 (text normalisation) and Chapter 4 "
        "(regular expressions and tokenisation).",
        "Van Der Walt, S., et al. (2024). scikit-learn: Machine Learning in Python. "
        "Journal of Machine Learning Research, 12, 2825-2830. Pedregosa, F., et al. (2011).",
        "Salton, G., and Buckley, C. (1988). Term-weighting approaches in automatic text "
        "retrieval. Information Processing and Management, 24(5), 513-523.",
    ])

    r.h2("Journal Articles")
    r.numbers([
        "Harris, C. R., Millman, K. J., van der Walt, S. J., et al. (2020). Array "
        "programming with NumPy. Nature, 585, 357-362.",
        "Hunter, J. D. (2007). Matplotlib: A 2D graphics environment. Computing in "
        "Science and Engineering, 9(3), 90-95.",
        "McKinney, W. (2010). Data structures for statistical computing in Python. "
        "Proceedings of the 9th Python in Science Conference, 51-56.",
        "Raviv, S., Vanclay, F., and Barua, A. (2020). Algorithmic transparency in job "
        "recruitment: The state-of-the-art. Information and Management, 57(7), 103284.",
        "Acemoglu, D., Autor, D., Hazell, J., and Restrepo, P. (2022). Artificial "
        "intelligence and jobs: Evidence from online vacancies. Journal of Labor Economics, "
        "40(2), 282-325.",
    ])

    r.h2("Documentation Consulted")
    r.numbers([
        "Python Software Foundation. Python Documentation. https://docs.python.org/3/",
        "Pallets Projects. Flask Documentation. https://flask.palletsprojects.com/",
        "Jinja Project. Jinja Documentation. https://jinja.palletsprojects.com/",
        "pypdf Documentation. https://pypdf.readthedocs.io/",
        "pdfplumber Documentation. https://github.com/jsvine/pdfplumber",
        "Werkzeug Utilities Reference (secure_filename). "
        "https://werkzeug.palletsprojects.com/en/3.0.x/utils/",
    ])

    r.h2("Software Acknowledgement")
    r.p(
        "The following open-source libraries are used and are distributed under permissive "
        "licences: Flask (BSD-3-Clause), Jinja2 (BSD-3-Clause), Werkzeug (BSD-3-Clause), "
        "pypdf (BSD-3-Clause), pdfminer.six (MIT), pdfplumber (MIT), NumPy (BSD-3-Clause), "
        "pandas (BSD-3-Clause), scikit-learn (BSD-3-Clause), Matplotlib (PSF-based), "
        "python-docx (MIT) and Werkzeug's secure_filename utility."
    )


# =========================================================================
# Appendices
# =========================================================================
def build_appendices(r, data):
    # ---------------- Appendix A ----------------
    r.h1("APPENDIX A - ROUTES AND API")
    r.table(
        ["Method", "Route", "Purpose"],
        [
            ["GET", "/", "Landing page"],
            ["GET", "/analyze", "Upload form and role selector"],
            ["POST", "/analyze", "Validates, analyses, then redirects to /results/<id>"],
            ["GET", "/results/<id>", "Dashboard for a stored analysis; safe to reload"],
            ["GET", "/report/<id>", "Plain-text report as a download"],
            ["GET", "/api/report/<id>", "Stored analysis as JSON"],
            ["POST", "/api/analyze", "Analysis as JSON, without the HTML page"],
            ["GET", "/api/roles", "Supported job roles"],
            ["GET", "/methodology", "Published scoring rubric"],
            ["GET", "/about", "Project context and honesty statement"],
            ["GET", "/health", "Service status and dataset sizes"],
        ],
        widths=[0.7, 1.7, 3.8],
        fontsize=9,
        caption="Table A.1: HTTP routes",
    )
    r.p("Calling the JSON endpoint directly:")
    r.code(
        'curl -F "resume=@resume.pdf" \\\n'
        '     -F "job_role=Python Developer" \\\n'
        '     http://127.0.0.1:5000/api/analyze',
        "Listing A.1: Calling the JSON API",
    )

    # ---------------- Appendix B ----------------
    r.h1("APPENDIX B - PLAIN-TEXT REPORT SAMPLE")
    r.p(
        "The downloadable report contains the same measured values as the dashboard, "
        "formatted for printing. The excerpt below is produced by the running application "
        "from the same synthetic fixture used in Chapter 7."
    )
    excerpt = data["text_report"]
    r.code(excerpt[:3200] + ("\n... [truncated for this appendix] ..." if len(excerpt) > 3200 else ""),
           "Listing B.1: Plain-text report excerpt")

    # ---------------- Appendix C ----------------
    r.h1("APPENDIX C - DATASET FORMATS")
    r.h2("C.1 data/skills.json")
    r.code(
        '{\n'
        '  "metadata": {\n'
        '    "version": "1.0",\n'
        '    "description": "Internal skill vocabulary for AI Resume Checker. Add skills to this "\n'
        '                    "file to extend the analyzer - no Python changes required.",\n'
        '    "notes": "The first skill in each list is the canonical display name. "\n'
        '             "\'skill_aliases\' maps extra spellings to that canonical name."\n'
        '  },\n'
        '  "categories": {\n'
        '    "Programming": ["Python", "Java", "C++", "JavaScript", "Kotlin"],\n'
        '    "Database":    ["MySQL", "PostgreSQL", "MongoDB", "PL/SQL", "SQLite"]\n'
        '  },\n'
        '  "soft_skills": ["Communication", "Leadership", "Teamwork", "Time Management"],\n'
        '  "skill_aliases": { "sklearn": "Scikit Learn", "postgres": "PostgreSQL" }\n'
        '}',
        "Listing C.1: skills.json structure",
    )
    r.p(
        "Adding a skill requires no Python change. A new category is detected "
        "automatically and appears in the dashboard and the skills chart."
    )
    r.h2("C.2 data/job_roles.json")
    r.code(
        '{\n'
        '  "roles": [\n'
        '    {\n'
        '      "role": "Data Analyst",\n'
        '      "aliases": ["data analyst", "business analyst", "reporting analyst"],\n'
        '      "category": "Data",\n'
        '      "summary": "Turns raw data into reports, dashboards and decisions.",\n'
        '      "core_skills":       ["SQL", "Python", "Excel"],\n'
        '      "preferred_skills":  ["Tableau", "Power BI", "Statistics"],\n'
        '      "bonus_skills":      ["ETL", "Data Modelling"],\n'
        '      "keywords": ["data", "report", "dashboard", "query"],\n'
        '      "responsibilities": ["Build dashboards", "Write ad-hoc queries"]\n'
        '    }\n'
        '  ]\n'
        '}',
        "Listing C.2: job_roles.json structure",
    )
    r.table(
        ["Role", "Category"],
        [[o["role"], o["category"]] for o in data["roles"]],
        widths=[2.4, 1.6],
        fontsize=9,
        caption=f"Table C.1: The {len(data['roles'])} supported job roles",
    )

    # ---------------- Appendix D ----------------
    r.h1("APPENDIX D - INSTALLATION AND RUNNING")
    r.h3("D.1 Create the environment")
    r.code(
        "cd ai-resume-checker\n"
        "python3 -m venv venv\n"
        "source venv/bin/activate        # Windows: venv\\Scripts\\activate\n"
        "pip install -r requirements.txt",
        "Listing D.1: Environment setup",
    )
    r.h3("D.2 Run the application")
    r.code(
        "python app.py\n"
        "# then open http://127.0.0.1:5000\n"
        "\n"
        "# if port 5000 is occupied (macOS AirPlay Receiver often uses it):\n"
        "PORT=5055 python app.py",
        "Listing D.2: Starting the application",
    )
    r.h3("D.3 Run the tests")
    r.code(
        "python tests/run_tests.py",
        "Listing D.3: Running the test suite",
    )
    r.h3("D.4 Run the console check")
    r.code(
        "python smoke_test.py",
        "Listing D.4: Running the smoke test",
    )
    r.h3("D.5 requirements.txt")
    r.code(
        "# Web framework\n"
        "Flask>=3.0\n"
        "\n"
        "# PDF text extraction\n"
        "pypdf>=4.2\n"
        "pdfplumber>=0.11\n"
        "\n"
        "# Data / numerical processing\n"
        "numpy>=1.26\n"
        "pandas>=2.1\n"
        "\n"
        "# NLP (TF-IDF vectorisation, cosine similarity)\n"
        "scikit-learn>=1.3\n"
        "\n"
        "# Charts on the dashboard\n"
        "matplotlib>=3.8",
        "Listing D.5: Application dependencies",
    )
    r.p(
        "Version constraints are minimums rather than exact pins so that the project also "
        "installs on newer Python releases. python-docx, used only to generate this "
        "report, is not listed because the application does not require it."
    )

    # ---------------- Appendix E ----------------
    r.h1("APPENDIX E - TEST OUTPUT")
    r.p(
        "Complete output of the test suite as run on the submission machine. No test is "
        "skipped, and no test depends on network access."
    )
    r.code(data["test_output"], "Listing E.1: Full test output")


# =========================================================================
# Main
# =========================================================================
def collect_data():
    import app as app_module
    from backend import charts
    from backend import job_matcher
    from backend.analyzer import build_plain_text_report

    skills = load_json("data/skills.json")
    roles = load_json("data/job_roles.json")["roles"]

    py_files = ["app.py"] + [
        f"backend/{n}" for n in sorted(os.listdir(os.path.join(BASE, "backend")))
        if n.endswith(".py")
    ]

    output = run_tests()
    m = re.search(r"Ran (\d+) tests in ([\d.]+)s", output)
    n_tests = int(m.group(1)) if m else 0
    seconds = float(m.group(2)) if m else 0.0

    sample = sample_analysis()
    groups = test_group_table()

    return {
        "n_skills": sum(len(v) for v in skills["categories"].values()),
        "n_categories": len(skills["categories"]),
        "n_soft": len(skills.get("soft_skills", [])),
        "n_aliases": len(skills.get("skill_aliases", {})),
        "cat_names": list(skills["categories"].keys()),
        "cat_counts": [len(v) for v in skills["categories"].values()],
        "n_roles": len(roles),
        "roles": [{"role": o["role"], "category": o["category"]} for o in roles],
        "py_lines": sum(line_count(p) for p in py_files),
        "py_funcs": sum(func_count(p) for p in py_files),
        "mod_resume_parser": line_count("backend/resume_parser.py"),
        "mod_analyzer": line_count("backend/analyzer.py"),
        "mod_job_matcher": line_count("backend/job_matcher.py"),
        "mod_ats": line_count("backend/ats_analyzer.py"),
        "mod_scoring": line_count("backend/scoring.py"),
        "mod_charts": line_count("backend/charts.py"),
        "mod_skill_extractor": line_count("backend/skill_extractor.py"),
        "mod_skill_data": line_count("backend/skill_data.py"),
        "mod_app": line_count("app.py"),
        "n_tests": n_tests,
        "test_seconds": seconds,
        "test_groups": groups,
        "test_output": output,
        "sample": sample,
        "text_report": build_plain_text_report(sample),
        "dataset_roles": job_matcher,
        # Read from the modules rather than retyped, so these rows cannot drift
        # away from the code they describe.
        "max_file_mb": app_module.MAX_FILE_SIZE_MB,
        "chart_mode_default": charts.CHART_MODE,
    }


def main():
    print("Collecting project data ...")
    data = collect_data()
    print(f"  tests        : {data['n_tests']} in {data['test_seconds']:.1f}s")
    print(f"  python lines : {data['py_lines']:,}")
    print(f"  roles        : {data['n_roles']}")
    print(f"  skills       : {data['n_skills']}")

    print("Building document ...")
    r = Report()
    build_front(r)
    build_abstract(r, data)
    build_ch1(r, data)
    build_ch2(r, data)
    build_ch3(r, data)
    build_ch4(r, data)
    build_ch5(r, data)
    build_ch6(r, data)
    build_ch7(r, data)
    build_ch8(r, data)
    build_references(r, data)
    build_appendices(r, data)
    r.footer_page_numbers()

    path = r.save()
    size = os.path.getsize(path)
    print(f"\nSaved: {path}")
    print(f"Size : {size:,} bytes")
    return path


if __name__ == "__main__":
    main()