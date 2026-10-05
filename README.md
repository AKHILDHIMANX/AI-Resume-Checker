# AI Resume Checker — AI-Based Resume Analyzer

> **MCA Semester 1 Project · Python Programming**

Upload a PDF resume. AI Resume Checker extracts the text with `pypdf` / `pdfplumber`, cleans it,
detects the sections, matches the skills that are actually written on the page, scores the
document against a published rubric, renders charts, and optionally compares the resume with
a target job role using weighted skill coverage and TF-IDF cosine similarity.

No API key is required. No account. No database. No JavaScript framework.

---

## Table of contents

1. [What it does](#1-what-it-does)
2. [Features](#2-features)
3. [Tech stack](#3-tech-stack)
4. [Project structure](#4-project-structure)
5. [Setup and running](#5-setup-and-running)
6. [Configuration](#6-configuration)
7. [How the analysis works](#7-how-the-analysis-works)
8. [Scoring explained](#8-scoring-explained)
9. [Extending the skill vocabulary](#9-extending-the-skill-vocabulary)
10. [Adding a job role](#10-adding-a-job-role)
11. [API endpoints](#11-api-endpoints)
12. [Tests](#12-tests)
13. [Project status](#13-project-status)
14. [Honest limitations](#14-honest-limitations)
15. [Privacy and security](#15-privacy-and-security)
16. [Future scope](#16-future-scope)

---

## 1. What it does

The pipeline runs nine stages on every upload:

| # | Stage | Implementation |
|---|-------|----------------|
| 1 | Upload & validation | MIME type + extension + size check, safe random filename |
| 2 | Text extraction | `pypdf`, with `pdfplumber` as fallback |
| 3 | Cleaning | Ligature, bullet, quote and line-wrap normalisation |
| 4 | Section detection | Regex against ~60 standard heading spellings |
| 5 | Field extraction | Regex for email, phone, links, degrees, institutions, years, CGPA, date ranges |
| 6 | Skill matching | Word-boundary-aware regex + alias map from `data/skills.json` |
| 7 | Keyword weighting | TF-IDF via scikit-learn, with a frequency fallback |
| 8 | Scoring & matching | Weighted sub-checks + cosine similarity against the selected role |
| 9 | Charts | matplotlib (Agg) rendered to PNG |

Every number on the dashboard traces back to a specific measurement. There are no
hard-coded results and no random scores.

---

## 2. Features

**Analysis**

- **Overall score (0–100)** — weighted blend of Structure, Content, Skills and ATS, with every
  sub-check and its point value shown in the dashboard.
- **Score radar** — spider plot of the four components plus overall, so one weak axis is visible
  instead of hidden inside an average.
- **ATS compatibility estimate** — eight documented readability checks worth 100 points, shown as
  a heat grid *and* a radar shape.
- **Skills map** — technical skills grouped by category, soft skills, action verbs, quantified
  results and vague-phrasing count.
- **Keyword analysis** — TF-IDF ranking and raw frequency, rendered as proportional bars.
- **Job role similarity** — weighted skill coverage (65%) + TF-IDF cosine similarity (35%),
  with matched and missing skills listed by importance tier.
- **All-role ranking** — the resume is compared against every role in the dataset, not only the
  selected one.
- **Prioritised fixes** — strengths, weaknesses and a ranked recommendation list.
- **Downloadable text report** — the same numbers as a `.txt` file.

**Interface**

- Light and dark themes with a no-flash inline theme bootstrap.
- Light/dark toggle persisted in `localStorage`.
- Sticky in-page navigation for the long dashboard.
- CSS 3D depth: layered elevation shadows, specular top-edge highlights, extruded score gauges,
  recessed meter tracks with glossy fills, tilted radar "pedestals", pointer tilt on cards.
- Counter animations, scroll reveals, responsive down to 360 px, `prefers-reduced-motion` support,
  and a print stylesheet.
- All motion is progressive enhancement — the server-rendered page works with JavaScript disabled.

---

## 3. Tech stack

| Layer | Tool |
|-------|------|
| Language | Python 3.9+ (developed on 3.14) |
| Web framework | Flask |
| Templates | Jinja2 |
| PDF parsing | pypdf, pdfplumber |
| Numerical | NumPy, pandas |
| NLP | scikit-learn (TF-IDF, cosine similarity) |
| Charts | Matplotlib (`Agg` backend, PNG output) |
| Front end | HTML5, CSS3, vanilla JavaScript — no framework, no build step |
| Tests | `unittest` (standard library) |
| Database | None, by design |

Deliberately absent: JavaScript frameworks, CSS frameworks, build tools, databases, and any
required external API.

---

## 4. Project structure

```
AI Resume Checker/
├── app.py                      # Flask entry point, routes, validation, error handling
├── requirements.txt
├── README.md
├── .gitignore
├── vercel.json                 # Deployment config: function size, env, file exclusions
├── .python-version             # Python version pinned for the deployment platform
│
├── backend/                    # All analysis logic (no web concerns)
│   ├── __init__.py
│   ├── skill_data.py           # Loads and validates the JSON datasets
│   ├── resume_parser.py        # PDF extraction, cleaning, sections, fields, metrics
│   ├── skill_extractor.py      # Skill matching, aliases, TF-IDF, verbs, quantifiers
│   ├── job_matcher.py          # Role loading, weighted coverage, cosine similarity
│   ├── ats_analyzer.py         # The eight ATS readability checks
│   ├── scoring.py              # Weights, sub-checks, grade bands
│   ├── analyzer.py             # Orchestration, advice, plain-text report
│   └── charts.py               # matplotlib chart builders
│
├── data/                       # Editable datasets — no code change needed
│   ├── skills.json             # 10 categories, 164 skills, 23 soft skills, 105 aliases
│   └── job_roles.json          # 10 job roles with core / preferred / bonus skills
│
├── templates/
│   ├── base.html               # Layout, theme toggle, nav, flash messages, footer
│   ├── _macros.html            # Reusable markup: rings, meters, heat cells, charts
│   ├── index.html              # Landing page
│   ├── upload.html             # Upload + role picker
│   ├── results.html            # The analysis dashboard (9 sections)
│   ├── methodology.html        # Every scoring rule, published
│   ├── about.html              # Project context and honesty statement
│   └── error.html              # 404 / 413 / 500 page
│
├── public/
│   └── static/                  # Served from the CDN in front of the app
│       ├── css/style.css        # Single stylesheet, design tokens, both themes
│       ├── js/script.js         # Theme, nav, tilt, counters, reveal, upload, print
│       └── img/
│           ├── favicon.svg
│           └── charts/          # Generated at runtime (git-ignored)
│
├── uploads/                    # Temporary uploads, deleted after analysis (git-ignored)
├── reports/                    # Generated .json / .txt reports (git-ignored)
│
├── tests/
│   ├── helpers.py              # Builds real in-memory PDF fixtures
│   ├── test_resume_parser.py
│   ├── test_skill_extractor.py
│   ├── test_scoring.py
│   ├── test_job_matcher.py
│   ├── test_app.py
│   └── run_tests.py            # Test entry point
│
├── smoke_test.py               # Optional dev helper: runs the pipeline end to end
│
└── docs/
    ├── AI_Resume_Checker_Project_Report.docx   # Academic project report (submission artifact)
    └── generate_report.py             # Regenerates the .docx from the real project files
```

---

## 5. Setup and running

### Requirements

- Python 3.9 or newer
- No system packages needed

### Install

```bash
cd ai-resume-checker

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Run

```bash
python app.py
```

Open **<http://127.0.0.1:5000>**

If port 5000 is already in use (common on macOS, where AirPlay Receiver listens on it):

```bash
PORT=5055 python app.py
```

### Run the tests

```bash
python tests/run_tests.py
```

### Run the smoke test

```bash
python smoke_test.py
```

### Regenerate the project report

The Word report in `docs/` is built from the live codebase, so its tables always match the
code. `python-docx` is the only dependency needed for this and is **not** required to run the
application:

```bash
pip install python-docx
python docs/generate_report.py
```

### Deploying

The repository is <https://github.com/AKHILDHIMANX/AI-Resume-Checker>, and it deploys to
Vercel on every push to `main`, so editing Git and republishing the site are the same action.

Vercel detects `app.py` defining `app` and runs it as a Python function; `vercel.json` sets the
function size, environment and which files to leave out of the bundle, and `.python-version`
pins the interpreter. Two settings make the difference between working and broken on a
serverless host:

| Setting | Value | Why |
|---------|-------|-----|
| `CHART_MODE` | `inline` (automatic) | Vercel mounts the project read-only and gives each instance its own temporary directory, so a PNG written to disk may be requested from a different instance that never had it. Charts are returned as base64 data URIs instead, and no chart file is ever written. The app detects `VERCEL` and picks this mode itself. |
| `MAX_FILE_MB` | `4` | Vercel rejects any request body above 4.5 MB. A 4 MB limit leaves room for the multipart boundary and filename. |

Storage is probed rather than assumed: `uploads/` and `reports/` are written to the project
directory when it is writable and to the system temporary directory when it is not, and the
twenty most recent analyses are also held in memory. A saved analysis therefore works
immediately after an upload on either host. What does change is persistence — a temporary
directory and a process both disappear with the instance, so on Vercel a `/results/<id>` URL
revisited after the instance is recycled shows *"no longer available"* and asks the user to
upload again. Nothing else regresses: uploads are still deleted after analysis, every score is
computed the same way, and the dashboard, the downloadable report and the JSON API all behave
identically.

Deploy manually once with the Vercel CLI, then every push afterwards updates the site:

```bash
npm install -g vercel        # or npx vercel
vercel login
vercel link                  # associates this directory with a Vercel project
vercel --prod                # first deployment
```

---

## 6. Configuration

Everything has a working default. Set these as environment variables only — never commit them.

| Variable | Default | Purpose |
|----------|---------|---------|
| `HOST` | `127.0.0.1` | Bind address |
| `PORT` | `5000` | Port |
| `SECRET_KEY` | random per start | Flask session signing |
| `FLASK_DEBUG` | `0` | Set to `1` for auto-reload and the debugger |
| `MAX_FILE_MB` | `4` | Upload size limit. Kept under the 4.5 MB request-body cap some hosts enforce |
| `STORAGE_DIR` | project directory | Where `uploads/` and `reports/` are written. Probed at start-up and replaced with a temporary directory when the project directory is read-only |
| `CHART_MODE` | `file`, or `inline` on Vercel | `file` writes a PNG and returns a URL; `inline` returns a base64 data URI and never touches the filesystem. Switches to `inline` automatically when `VERCEL` is set, so no configuration is needed on the first deploy |
| `KEEP_UPLOADS` | `0` | Set to `1` to keep uploaded PDFs (debugging only) |
| `ENABLE_AI_ASSIST` | `0` | Set to `1` to enable the optional LLM polish |
| `OPENAI_API_KEY` | unset | Enables OpenAI polish when combined with the flag |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model used for polish |
| `GEMINI_API_KEY` | unset | Enables Gemini polish when combined with the flag |
| `GEMINI_MODEL` | `gemini-1.5-flash` | Model used for polish |
| `AI_REQUEST_TIMEOUT` | `8` | Seconds before giving up on the API |

**The AI assist is genuinely optional.** With no key and no flag, everything runs on local
rules. If a call fails or times out, the local advice is used unchanged — the app never shows
invented text and never blocks on the network. It is used to rephrase advice, never to invent
scores.

Example:

```bash
ENABLE_AI_ASSIST=1 OPENAI_API_KEY=sk-... PORT=5055 python app.py
```

---

## 7. How the analysis works

### Text extraction

`pypdf` reads the text layer first. If it returns too little text, `pdfplumber` is used to
recover what was missed. A PDF that is password-protected, corrupt, empty or image-only raises a
typed error that the UI turns into a plain-English message — never a traceback.

### Cleaning

Ligatures (`ﬁ` → `fi`), smart quotes, non-breaking spaces, repeated bullet glyphs and hyphenated
line wraps are normalised so that downstream matching sees consistent text.

### Section detection

Each line is normalised (lowercased, punctuation stripped) and compared against a lookup table of
standard headings and their common spellings. Headings that combine sections
(`ACHIEVEMENTS AND PROJECTS`) are recognised, and a heading is never reported back to the user as
if it were content.

### Skill matching

Every skill in `data/skills.json` is compiled into a regex whose boundary class excludes `/`, so
`PL/SQL`, `CI/CD` and `Node.js` survive intact. A leading boundary is required so `C` is not
credited for `C++`. Aliases (`sklearn` → Scikit Learn, `postgres` → PostgreSQL) map alternate
spellings onto the canonical name.

### Keyword extraction

The resume is split into sentences and vectorised with `TfidfVectorizer`. Terms that stand out
*within this document* score highest. If scikit-learn is unavailable, a frequency-based fallback
keeps the section working.

### Job matching

```
match_score = 0.65 × weighted_skill_coverage + 0.35 × tfidf_cosine_similarity
```

Weighted skill coverage counts core skills ×3, preferred ×2 and bonus ×1. Each skill belongs to
exactly one tier, so a skill listed twice in the dataset is counted once.

---

## 8. Scoring explained

### Overall

```
Overall = 0.30 × Structure + 0.25 × Content + 0.25 × Skills + 0.20 × ATS estimate
```

| Band | Score |
|------|-------|
| Excellent | 90–100 |
| Very Good | 80–89 |
| Good | 70–79 |
| Needs Improvement | 60–69 |
| Weak | 40–59 |
| Very Weak | 0–39 |

**Job Match is reported separately and never affects the overall score.** It only exists when a
target role has been chosen.

### Components

| Component | Sub-checks |
|-----------|-----------|
| **Structure** (0.30) | sections present · contact completeness · standard headings · content organisation |
| **Content** (0.25) | length · action verbs · measurable results · sentence readability · vague phrasing |
| **Skills** (0.25) | technical breadth · skill specificity · soft skills · keyword strength |
| **ATS estimate** (0.20) | headings · contact info · text readability · length · formatting noise · bullets · keywords · completeness |

The in-app **Methodology** page prints every sub-check, its weight and its rule, and the
dashboard prints the points each one actually earned.

---

## 9. Extending the skill vocabulary

Edit `data/skills.json` — no Python changes required. Reload the page.

```jsonc
{
  "categories": {
    "Programming": ["Python", "Java", "My New Language"]
  },
  "soft_skills": ["Communication"],
  "skill_aliases": {
    "mylang": "My New Language"   // alternate spelling -> canonical name
  }
}
```

The first entry in a list is the canonical display name. Add a category and it appears in the
dashboard and the skills chart automatically.

---

## 10. Adding a job role

Edit `data/job_roles.json`:

```jsonc
{
  "role": "Data Analyst",
  "category": "Data",
  "summary": "Turns raw data into reports and dashboards.",
  "core_skills":     ["SQL", "Python", "Excel"],
  "preferred_skills": ["Tableau", "Power BI"],
  "bonus_skills":     ["Statistics"],
  "responsibilities": ["Build dashboards", "Write ad-hoc queries"],
  "keywords": ["data", "report", "dashboard", "sql"]
}
```

A role appears in the upload dropdown, in the all-role ranking and in `/api/roles` on the next
page load. Keep each skill in exactly one tier to avoid ambiguity — the matcher de-duplicates
across tiers anyway, keeping the highest.

---

## 11. API endpoints

| Method | Route | Returns |
|--------|-------|---------|
| `GET` | `/` | Landing page |
| `GET` | `/analyze` | Upload form |
| `POST` | `/analyze` | Runs the analysis, redirects to `/results/<id>` |
| `GET` | `/results/<id>` | Dashboard for a stored analysis (reloadable) |
| `GET` | `/report/<id>` | Plain-text report as a download |
| `GET` | `/api/report/<id>` | Full analysis JSON |
| `POST` | `/api/analyze` | Analysis JSON without the HTML page |
| `GET` | `/api/roles` | Job role list |
| `GET` | `/methodology` | Published scoring rules |
| `GET` | `/about` | Project context |
| `GET` | `/health` | Status and dataset sizes |

Example:

```bash
curl -F "resume=@resume.pdf" -F "job_role=Python Developer" \
     http://127.0.0.1:5000/api/analyze
```

Errors always return a JSON body with an `ok: false` flag and a human-readable `error` message.

---

## 12. Tests

```bash
$ python tests/run_tests.py
...
Ran 145 tests in 13.1s

OK
```

The suite generates real PDF fixtures in memory with matplotlib — no sample files are committed.
It covers:

- PDF extraction, cleaning, metrics and section detection
- Graceful failure on empty, corrupt and image-only PDFs
- Skill matching, alias resolution and word-boundary correctness
- Score bounds, weight arithmetic and grade bands
- Job matching, deduplication and unknown-role handling
- Every route, including the error paths, asserting that no traceback ever reaches the user

---

## 13. Project status

| Area | Status |
|------|--------|
| PDF parsing with `pypdf` + `pdfplumber` fallback | Complete |
| Text cleaning and section detection | Complete |
| Regex field extraction | Complete |
| Skill matching with aliases and safe boundaries | Complete |
| TF-IDF keywords and cosine similarity | Complete |
| 10 job roles, 164 skills, 10 categories | Complete |
| Transparent weighted scoring, all rules published | Complete |
| ATS compatibility estimate (8 checks) | Complete |
| 7 charts including 2 radar plots | Complete |
| Dashboard with light/dark themes | Complete |
| Validation, safe filenames, upload deletion | Complete |
| Optional AI assist, off by default | Complete |
| Test suite | 145 tests, all passing |
| Database, accounts, email, deployment | Not implemented, by design |

---

## 14. Honest limitations

- **Text only.** A scanned or image-only PDF produces a clear error instead of a guess. There is
  no OCR.
- **Vocabulary-bound.** Only skills listed in `data/skills.json` can be detected. A technology
  that is missing from that file is invisible to the analyzer.
- **Heading-dependent.** Section detection needs headings as text. A resume whose headings are
  images is not parsed correctly.
- **Heuristic records.** Experience, project and education parsing merges entries heuristically,
  so a multi-line role can be split oddly.
- **The ATS number is an estimate.** It is built from general readability practices. It does not
  reproduce any specific company or vendor ATS, and passing it guarantees nothing.
- **No hiring claim.** Resume match is a text and keyword comparison. It is never a statement that
  a candidate is qualified or unqualified for a role.
- **English, single-column, text-based PDFs** are the supported input.

---

## 15. Privacy and security

- File type is validated by MIME type, extension **and** PDF magic bytes before parsing.
- Uploads are renamed to a random safe filename; the original name is never used on disk.
- `uploads/` is never served statically.
- Uploads are deleted immediately after analysis (`KEEP_UPLOADS=1` opts out for debugging).
- Report files are written with a timestamped id and are not listed anywhere.
- No API key is stored in source; keys come from environment variables only.
- No third-party service receives the resume unless the optional AI assist is explicitly enabled,
  and even then only the extracted text needed for polishing.
- 413, 404 and 500 handlers return friendly pages and never leak a traceback.

---

## 16. Future scope

- OCR support for scanned PDFs
- DOCX support
- Side-by-side comparison of two resume versions
- A role-import tool that reads a pasted job description
- Per-section rewrite suggestions
- A localisation pass for regional-language resumes

---

## License

Academic project, submitted for assessment. Provided as-is for educational use.

**Built for an MCA Semester 1 Python Programming submission.**