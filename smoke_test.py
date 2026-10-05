"""
Quick smoke test for the analysis pipeline.

Generates a synthetic resume PDF (no personal data), runs the full pipeline
and prints the report so the output can be inspected. This file is a
development helper - the real automated tests live in ``tests/``.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.analyzer import analyze_resume, build_plain_text_report  # noqa: E402
from backend.charts import generate_all_charts  # noqa: E402
from backend.resume_parser import parse_resume  # noqa: E402
from backend.skill_extractor import extract_skills  # noqa: E402


def make_pdf(path: str) -> str:
    """Build a small text-based PDF using matplotlib's PDF backend."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    text = """John Doe
john.doe@example.com | +91 98765 43210 | Chandigarh, India
linkedin.com/in/johndoe | github.com/johndoe

PROFESSIONAL SUMMARY
Final year MCA student with hands-on experience in Python and Java application
development. Built academic projects using Flask, MySQL and REST APIs. Strong
interest in data structures, databases and clean code development.

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
  engine with TF-IDF and cosine similarity, 3 team members
- Student Attendance System in Python and MySQL, reduced manual register
  entry by 60%

INTERNSHIP
Software Developer Intern, Tech Solutions Pvt Ltd - June 2024 to December 2024
- Developed REST API endpoints in Flask for a college management system
- Wrote 40+ SQL queries to generate automated attendance and grade reports
- Improved page load time by 35% by adding pagination and caching

CERTIFICATIONS
- Oracle PL/SQL Programming, Oracle University, 2023
- Python for Data Science, Coursera, 2024

ACHIEVEMENTS
- First prize in Inter-College Hackathon, 2024
- Dean's List academic excellence

LANGUAGES
English - Fluent
Hindi - Native

INTERESTS
Web Development, Open Source, Chess
"""

    fig = plt.figure(figsize=(8.27, 11.69))
    fig.text(0.07, 0.95, text, va="top", ha="left", fontsize=7.4, family="monospace",
             linespacing=1.45)
    fig.savefig(path, format="pdf")
    plt.close(fig)
    return path


if __name__ == "__main__":
    pdf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "_smoke_resume.pdf")
    make_pdf(pdf_path)
    data = open(pdf_path, "rb").read()
    print(f"Generated sample PDF: {len(data)} bytes\n")

    resume = parse_resume(data)
    print("PARSED")
    print("  pages          :", resume.pages)
    print("  words          :", resume.word_count)
    print("  name           :", resume.contact.name)
    print("  emails         :", resume.contact.emails)
    print("  phones         :", resume.contact.phones)
    print("  links          :", resume.contact.links[:3])
    print("  sections found :", resume.sections_found)
    print("  education      :", [e.degree for e in resume.education])
    print("  experience     :", [e.title for e in resume.experience])
    print("  projects       :", [p.name for p in resume.projects][:3])
    print("  certifications :", [c.name for c in resume.certifications])
    print("  languages      :", resume.languages_listed)
    print("  interests      :", resume.interests)

    profile = extract_skills(resume.clean_text, resume.section_text)
    print("\nSKILLS")
    for category, items in profile.technical_by_category.items():
        print(f"  {category:<18}: {', '.join(items)}")
    print(f"  {'Soft':<18}: {', '.join(profile.soft)}")
    print(f"  action verbs    : {profile.action_verbs[:8]}")
    print(f"  quantifiers     : {profile.quantifier_count}")
    print(f"  keywords        : {[k['term'] for k in profile.keywords[:8]]}")

    result = analyze_resume(data, job_role="Python Developer", filename="sample.pdf")
    print("\nSCORES")
    print("  overall :", result["scores"]["overall"], result["scores"]["grade"])
    for component in result["scores"]["components"]:
        print(f"  {component['label']:<18}: {component['score']}")
    print("  ats     :", result["ats"]["score"])
    job = result["job_match"]
    print("  job     :", job["role"], job["match_score"])
    print("  matched :", job["matched_skills"])
    print("  missing :", job["missing_skills"])
    print("  charts  :", list(result["charts"].keys()))
    print("  roles   :", [(r["role"], r["score"]) for r in result["role_overview"]][:3])

    print("\n" + build_plain_text_report(result)[:2000])

    os.remove(pdf_path)
    print("\nSmoke test finished.")