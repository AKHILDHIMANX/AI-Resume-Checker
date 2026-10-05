"""
End-to-end and HTTP-layer tests.

Covers upload validation, invalid file handling, error pages and the full
analysis pipeline running against a real generated PDF.
"""

import io
import os
import subprocess
import sys
import unittest

from tests.helpers import (
    corrupted_pdf,
    empty_pdf,
    minimal_pdf_bytes,
    no_skills_pdf_bytes,
    not_a_pdf,
    sample_pdf_bytes,
)

import app as resume_app
from backend import charts as chart_module
from backend.analyzer import AnalysisError, analyze_resume, build_plain_text_report
from backend.job_matcher import UnknownRoleError
from backend.resume_parser import EmptyPDFError, InvalidPDFError


class TestFullPipeline(unittest.TestCase):
    def setUp(self):
        self.data = sample_pdf_bytes()

    def test_analysis_returns_expected_sections(self):
        result = analyze_resume(self.data, "Python Developer", "test.pdf")
        for key in ("meta", "overview", "skills", "scores", "ats", "job_match",
                    "advice", "charts", "missing_sections", "role_overview"):
            self.assertIn(key, result)

    def test_scores_are_sane(self):
        result = analyze_resume(self.data, "Python Developer", "test.pdf")
        scores = result["scores"]
        self.assertGreaterEqual(scores["overall"], 0)
        self.assertLessEqual(scores["overall"], 100)
        self.assertEqual(len(scores["components"]), 4)
        self.assertGreaterEqual(result["ats"]["score"], 0)
        self.assertLessEqual(result["ats"]["score"], 100)

    def test_advice_blocks_are_populated(self):
        result = analyze_resume(self.data, "Python Developer", "test.pdf")
        advice = result["advice"]
        self.assertTrue(advice["strengths"])
        self.assertTrue(advice["weaknesses"])
        self.assertTrue(advice["recommendations"])
        for bucket in ("strengths", "weaknesses", "recommendations"):
            for item in advice[bucket]:
                self.assertTrue(item["title"])
                self.assertTrue(item["detail"])
                self.assertIn(item["priority"], ("High", "Medium", "Low"))

    def test_analysis_without_role(self):
        result = analyze_resume(self.data, None, "test.pdf")
        self.assertIsNone(result["job_match"])
        self.assertIsNone(result["job_match_error"])
        self.assertIn("scores", result)

    def test_unknown_role_is_reported_not_raised(self):
        result = analyze_resume(self.data, "Astronaut Trainer", "test.pdf")
        self.assertIsNone(result["job_match"])
        self.assertIn("not one of the available", result["job_match_error"])

    def test_result_is_json_serialisable(self):
        import json

        result = analyze_resume(self.data, "Data Analyst", "test.pdf")
        json.dumps(result)  # must not raise

    def _assert_chart_reference(self, url):
        """A chart reference is valid in whichever mode is active.

        File mode returns a ``/static/...`` URL that must exist on disk. Inline
        mode returns a base64 ``data:`` URI, which has no file behind it by
        design, so only its shape can be checked.
        """
        if chart_module.INLINE_CHARTS:
            self.assertTrue(url.startswith("data:image/png;base64,"), msg=url[:40])
            self.assertGreater(len(url), len("data:image/png;base64,") + 64)
            return
        self.assertTrue(url.startswith("/static/img/charts/"))
        # Resolved against the configured static folder, not the project root,
        # so this keeps working wherever public/ is pointed.
        served = os.path.join(
            resume_app.app.static_folder,
            url.split(resume_app.app.static_url_path + "/", 1)[1],
        )
        self.assertTrue(os.path.isfile(served), msg=f"missing chart file {served}")

    def test_charts_are_generated(self):
        result = analyze_resume(self.data, "Python Developer", "test.pdf")
        self.assertIn("scores", result["charts"])
        self.assertIn("skills", result["charts"])
        for url in result["charts"].values():
            self._assert_chart_reference(url)

    def test_every_chart_of_one_analysis_is_kept(self):
        """The cleanup cap must not delete a report's own charts."""
        result = analyze_resume(self.data, "Python Developer", "test.pdf")
        for url in result["charts"].values():
            self._assert_chart_reference(url)

    @unittest.skipIf(
        chart_module.INLINE_CHARTS,
        "inline mode never writes a PNG, so there is nothing to bound",
    )
    def test_chart_folder_stays_bounded(self):
        """Repeated analyses must not grow the chart folder without limit."""
        for _ in range(4):
            analyze_resume(self.data, "Python Developer", "test.pdf")
        pngs = [
            name
            for name in os.listdir(chart_module.STATIC_CHART_DIR)
            if name.endswith(".png")
        ]
        self.assertLessEqual(
            len(pngs),
            40,
            msg="chart cleanup did not run during chart generation",
        )

    def test_plain_text_report(self):
        result = analyze_resume(self.data, "Python Developer", "test.pdf")
        report = build_plain_text_report(result)
        self.assertIn("AI Resume Checker", report)
        self.assertIn("Overall Resume Score", report)
        self.assertIn("Job Match Score", report)

    def test_analysis_is_reproducible(self):
        first = analyze_resume(self.data, "DevOps Engineer", "t.pdf")["scores"]["overall"]
        second = analyze_resume(self.data, "DevOps Engineer", "t.pdf")["scores"]["overall"]
        self.assertEqual(first, second)

    def test_sparse_resume_still_analyses(self):
        """A two-section resume produces a result, not an error."""
        result = analyze_resume(minimal_pdf_bytes(), "Python Developer", "m.pdf")
        missing = {item["key"] for item in result["missing_sections"]}
        self.assertIn("education", missing)
        self.assertIn("experience", missing)
        self.assertNotIn("skills", missing)  # the sample does have a Skills heading
        self.assertGreater(result["scores"]["overall"], 0)
        self.assertLessEqual(result["scores"]["overall"], 100)

    def test_skillless_resume_still_analyses(self):
        result = analyze_resume(no_skills_pdf_bytes(), "Data Analyst", "n.pdf")
        self.assertEqual(result["skills"]["technical"], [])
        self.assertGreater(len(result["advice"]["recommendations"]), 3)


class TestErrorHandling(unittest.TestCase):
    def test_no_file_is_an_error(self):
        with self.assertRaises(InvalidPDFError):
            analyze_resume(not_a_pdf(), None, "cv.pdf")

    def test_corrupted_pdf_is_an_error(self):
        with self.assertRaises((InvalidPDFError, EmptyPDFError)):
            analyze_resume(corrupted_pdf(), None, "cv.pdf")

    def test_empty_pdf_is_an_error(self):
        with self.assertRaises(EmptyPDFError):
            analyze_resume(empty_pdf(), None, "cv.pdf")

    def test_zero_bytes_is_an_error(self):
        with self.assertRaises(EmptyPDFError):
            analyze_resume(b"", None, "cv.pdf")

    def test_unknown_role_is_reported_in_result(self):
        """An unknown role degrades gracefully: analysis still completes."""
        result = analyze_resume(sample_pdf_bytes(), "Galactic Chef", "test.pdf")
        self.assertIsNone(result["job_match"])
        self.assertIsNotNone(result["job_match_error"])
        self.assertIn("not one of the available", result["job_match_error"])
        self.assertIn("scores", result)

    def test_job_matcher_raises_for_unknown_role(self):
        from backend.job_matcher import match_job

        with self.assertRaises(UnknownRoleError):
            match_job(sample_pdf_bytes().decode("latin-1"), "Galactic Chef")


class TestFlaskRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        resume_app.app.config["TESTING"] = True
        resume_app.app.config["SECRET_KEY"] = "test-key"
        cls.client = resume_app.app.test_client()

    def test_index_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"AI Resume Checker", response.data)
        self.assertIn(b"Analyse a resume", response.data)

    def test_upload_form(self):
        response = self.client.get("/analyze")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Target job role", response.data)

    def test_methodology_page(self):
        response = self.client.get("/methodology")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Overall Resume Score", response.data)

    def test_about_page(self):
        response = self.client.get("/about")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"MCA Semester 1", response.data)

    def test_health_endpoint(self):
        payload = self.client.get("/health").get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertGreaterEqual(payload["roles_loaded"], 10)

    def test_roles_api(self):
        payload = self.client.get("/api/roles").get_json()
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(len(payload["roles"]), 10)

    def test_post_without_file_redirects_with_message(self):
        response = self.client.post("/analyze", data={}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"choose a PDF resume", response.data)

    def test_post_with_non_pdf_is_rejected(self):
        data = {
            "resume": (io.BytesIO(b"hello world this is a text file"), "resume.txt")
        }
        response = self.client.post("/analyze", data=data, content_type="multipart/form-data",
                                    follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"accepts PDF files only", response.data)

    def test_post_with_corrupted_pdf_shows_friendly_error(self):
        data = {"resume": (io.BytesIO(corrupted_pdf()), "broken.pdf")}
        response = self.client.post("/analyze", data=data, content_type="multipart/form-data",
                                    follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Traceback", response.data)
        self.assertIn(b"corrupt", response.data.lower())

    def test_post_with_image_only_pdf_shows_friendly_error(self):
        data = {"resume": (io.BytesIO(empty_pdf()), "scan.pdf")}
        response = self.client.post("/analyze", data=data, content_type="multipart/form-data",
                                    follow_redirects=True)
        self.assertNotIn(b"Traceback", response.data)
        self.assertIn(b"scanned", response.data.lower())

    def test_post_with_empty_file_is_rejected(self):
        data = {"resume": (io.BytesIO(b""), "empty.pdf")}
        response = self.client.post("/analyze", data=data, content_type="multipart/form-data",
                                    follow_redirects=True)
        self.assertIn(b"empty", response.data.lower())

    def test_full_workflow_renders_dashboard(self):
        data = {
            "resume": (io.BytesIO(sample_pdf_bytes()), "john_doe_resume.pdf"),
            "job_role": "Python Developer",
        }
        response = self.client.post("/analyze", data=data, content_type="multipart/form-data")
        # POST redirects to /results/<id> so the dashboard has a reloadable URL.
        self.assertEqual(response.status_code, 302)
        self.assertIn("/results/", response.headers["Location"])
        response = self.client.get(response.headers["Location"])
        self.assertEqual(response.status_code, 200)
        body = response.data
        self.assertIn(b"Analysis dashboard", body)
        self.assertIn(b"Overall score", body)
        self.assertIn(b"ATS compatibility", body)
        self.assertIn(b"Job match", body)
        self.assertIn(b"Skills detected", body)
        self.assertIn(b"Keywords", body)
        self.assertIn(b"Missing sections", body)
        self.assertIn(b"John Doe", body)
        self.assertNotIn(b"Traceback", body)

    def test_full_workflow_without_role(self):
        data = {"resume": (io.BytesIO(sample_pdf_bytes()), "cv.pdf")}
        response = self.client.post("/analyze", data=data, content_type="multipart/form-data",
                                    follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No target role was selected", response.data)

    def test_uploaded_file_is_deleted_after_analysis(self):
        before = os.listdir(resume_app.UPLOAD_DIR)
        data = {"resume": (io.BytesIO(sample_pdf_bytes()), "temp_resume.pdf")}
        self.client.post("/analyze", data=data, content_type="multipart/form-data")
        after = os.listdir(resume_app.UPLOAD_DIR)
        self.assertEqual(sorted(before), sorted(after))
        self.assertFalse(any(name.endswith("temp_resume.pdf") for name in after))

    def test_safe_upload_name_has_no_original_filename(self):
        name = resume_app.safe_upload_name("../../etc/pass wd.PDF")
        self.assertTrue(name.endswith(".pdf"))
        self.assertNotIn("/", name)
        self.assertNotIn("..", name)
        self.assertRegex(name, r"^[A-Za-z0-9_-]+_[0-9a-f]{10}\.pdf$")

    def test_safe_upload_name_is_unique(self):
        first = resume_app.safe_upload_name("resume.pdf")
        second = resume_app.safe_upload_name("resume.pdf")
        self.assertNotEqual(first, second)

    def test_allowed_file(self):
        self.assertTrue(resume_app.allowed_file("resume.pdf"))
        self.assertTrue(resume_app.allowed_file("RESUME.PDF"))
        self.assertFalse(resume_app.allowed_file("resume.docx"))
        self.assertFalse(resume_app.allowed_file("resume"))
        self.assertFalse(resume_app.allowed_file("resume.pdf.exe"))

    def test_looks_like_pdf_checks_the_signature(self):
        self.assertTrue(resume_app.looks_like_pdf(b"%PDF-1.7\nrest"))
        self.assertTrue(resume_app.looks_like_pdf(b"  \n%PDF-1.4"))
        self.assertFalse(resume_app.looks_like_pdf(b"just plain text"))
        self.assertFalse(resume_app.looks_like_pdf(b"\x89PNG\r\n\x1a\n"))
        self.assertFalse(resume_app.looks_like_pdf(b""))

    def test_text_file_renamed_to_pdf_is_rejected(self):
        """A .txt renamed to .pdf must be refused before the parser runs."""
        data = {"resume": (io.BytesIO(b"Dear hiring manager, I am writing..."),
                           "resume.pdf")}
        response = self.client.post("/analyze", data=data,
                                    content_type="multipart/form-data",
                                    follow_redirects=True)
        self.assertNotIn(b"Traceback", response.data)
        self.assertIn(b"does not look like a real PDF", response.data)

    def test_api_rejects_non_pdf_content_with_pdf_name(self):
        data = {"resume": (io.BytesIO(b"not a pdf at all"), "cv.pdf")}
        response = self.client.post("/api/analyze", data=data,
                                    content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["ok"])
        self.assertIn("PDF data", response.get_json()["error"])

    def test_api_analyze_returns_json(self):
        data = {
            "resume": (io.BytesIO(sample_pdf_bytes()), "cv.pdf"),
            "job_role": "Data Analyst",
        }
        response = self.client.post("/api/analyze", data=data,
                                    content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["job_match"]["role"], "Data Analyst")

    def test_api_analyze_rejects_non_pdf(self):
        data = {"resume": (io.BytesIO(b"plain text"), "cv.txt")}
        response = self.client.post("/api/analyze", data=data,
                                    content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["ok"])

    def test_api_analyze_without_file(self):
        response = self.client.post("/api/analyze", data={},
                                    content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)

    def test_404_page(self):
        response = self.client.get("/no-such-page")
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"Page not found", response.data)

    def test_report_download_after_analysis(self):
        data = {"resume": (io.BytesIO(sample_pdf_bytes()), "cv.pdf")}
        response = self.client.post("/analyze", data=data,
                                    content_type="multipart/form-data")
        self.assertEqual(response.status_code, 302)
        report_id = response.headers["Location"].split("/results/", 1)[1].split("?", 1)[0]

        download = self.client.get(f"/report/{report_id}")
        self.assertEqual(download.status_code, 200)
        self.assertIn(b"AI Resume Checker", download.data)
        self.assertIn("attachment", download.headers["Content-Disposition"])

        as_json = self.client.get(f"/api/report/{report_id}")
        self.assertEqual(as_json.status_code, 200)
        self.assertIn("scores", as_json.get_json())

    def test_missing_report_is_handled(self):
        response = self.client.get("/report/does_not_exist", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"no longer available", response.data)

    def test_results_page_is_reloadable_by_id(self):
        """The dashboard URL survives a refresh instead of re-uploading."""
        data = {"resume": (io.BytesIO(sample_pdf_bytes()), "cv.pdf"),
                "job_role": "Python Developer"}
        posted = self.client.post("/analyze", data=data,
                                  content_type="multipart/form-data")
        report_id = posted.headers["Location"].split("/results/", 1)[1].split("?", 1)[0]

        # Two independent GETs, as a browser refresh would do.
        for _ in range(2):
            page = self.client.get(f"/results/{report_id}")
            self.assertEqual(page.status_code, 200)
            self.assertIn(b"Analysis dashboard", page.data)
            self.assertIn(b"Overall score", page.data)
            # The PDF is gone, so the page must not need it a second time.
            self.assertNotIn(b"Traceback", page.data)

    def test_missing_results_id_redirects_to_upload(self):
        response = self.client.get("/results/nope", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"no longer available", response.data)
        self.assertIn(b"Target job role", response.data)

    def test_corrupt_stored_report_is_handled(self):
        data = {"resume": (io.BytesIO(sample_pdf_bytes()), "cv.pdf")}
        posted = self.client.post("/analyze", data=data,
                                  content_type="multipart/form-data")
        report_id = posted.headers["Location"].split("/results/", 1)[1].split("?", 1)[0]

        # Truncate the stored JSON the way a partial write would.
        path = os.path.join(resume_app.REPORTS_DIR, f"{report_id}.json")
        with open(path, "r+", encoding="utf-8") as handle:
            content = handle.read()
            handle.seek(0)
            handle.write(content[: len(content) // 2])
            handle.truncate()

        response = self.client.get(f"/results/{report_id}", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Traceback", response.data)
        self.assertIn(b"could not be read", response.data)

    def test_success_flash_is_shown_on_the_results_page(self):
        data = {"resume": (io.BytesIO(sample_pdf_bytes()), "cv.pdf")}
        response = self.client.post("/analyze", data=data,
                                    content_type="multipart/form-data",
                                    follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Analysis complete", response.data)
        self.assertIn(b"flash-success", response.data)


class TestServerlessStorage(unittest.TestCase):
    """Storage behaviour needed on a host with a read-only project directory.

    Vercel mounts the project read-only, so uploads, reports and chart PNGs
    cannot all be written and served the way they are on a normal machine.
    These tests pin the fallbacks so the app stays usable there.
    """

    def test_writable_dir_falls_back_when_preferred_location_is_unusable(self):
        """/dev/null is not a directory, so it can never be created under."""
        previous = os.environ.get("STORAGE_DIR")
        os.environ["STORAGE_DIR"] = "/dev/null/ai-resume-checker"
        try:
            chosen = resume_app._writable_dir()
        finally:
            if previous is None:
                os.environ.pop("STORAGE_DIR", None)
            else:
                os.environ["STORAGE_DIR"] = previous

        self.assertNotEqual(chosen, "/dev/null/ai-resume-checker")
        self.assertTrue(os.path.isdir(chosen), msg=f"fallback {chosen} is not a directory")
        self.assertTrue(os.access(chosen, os.W_OK), msg=f"fallback {chosen} is not writable")

    def test_report_is_remembered_when_the_reports_directory_is_unwritable(self):
        """A failed write must not make a finished analysis unreachable."""
        result = analyze_resume(sample_pdf_bytes(), "Python Developer", "cv.pdf")
        previous = resume_app.REPORTS_DIR
        resume_app.REPORTS_DIR = "/dev/null/ai-resume-checker/reports"
        try:
            resume_app._save_report(result, "readonly_probe")
            found, text, status = resume_app._recall_report("readonly_probe")
        finally:
            resume_app.REPORTS_DIR = previous

        self.assertEqual(status, "ok")
        self.assertIsNotNone(found)
        self.assertEqual(found["scores"]["overall"], result["scores"]["overall"])
        self.assertIn("AI Resume Checker", text)
        self.assertIn("Overall", text)

    def test_recall_distinguishes_missing_from_unreadable(self):
        """The two failures need different messages, so they need distinct states."""
        _result, _text, status = resume_app._recall_report("definitely_not_stored")
        self.assertEqual(status, "missing")

        previous = resume_app.REPORTS_DIR
        resume_app.REPORTS_DIR = "/dev/null/ai-resume-checker/reports"
        try:
            resume_app._save_report({"meta": {}, "scores": {}}, "truncated_probe")
        finally:
            resume_app.REPORTS_DIR = previous

        # A file that exists but holds invalid JSON must be reported as such
        # rather than quietly served from memory.
        resume_app._REPORT_CACHE.pop("truncated_probe", None)
        broken_dir = resume_app.REPORTS_DIR
        os.makedirs(broken_dir, exist_ok=True)
        with open(os.path.join(broken_dir, "truncated_probe.json"), "w",
                  encoding="utf-8") as handle:
            handle.write('{"scores": {"overall": ')
        try:
            _result, _text, status = resume_app._recall_report("truncated_probe")
        finally:
            os.remove(os.path.join(broken_dir, "truncated_probe.json"))
            resume_app._REPORT_CACHE.pop("truncated_probe", None)

        self.assertEqual(status, "unreadable")

    def test_inline_chart_mode_never_touches_the_filesystem(self):
        """Inline mode is checked in a subprocess because it is read at import."""
        script = (
            "import base64, os\n"
            "from backend import charts\n"
            "assert charts.INLINE_CHARTS, charts.CHART_MODE\n"
            "import matplotlib.pyplot as plt\n"
            "fig, ax = plt.subplots()\n"
            "ax.plot([1, 2, 3], [1, 4, 9])\n"
            "uri = charts._save(fig, 'probe')\n"
            "assert uri.startswith('data:image/png;base64,'), uri[:40]\n"
            "raw = base64.b64decode(uri.split(',', 1)[1])\n"
            "assert raw[:8] == b'\\x89PNG\\r\\n\\x1a\\n', raw[:8]\n"
            "print('inline-ok')\n"
        )
        env = dict(os.environ, CHART_MODE="inline")
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=resume_app.BASE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertIn("inline-ok", completed.stdout,
                      msg=completed.stderr[-800:])
        self.assertEqual(
            [n for n in os.listdir(chart_module.STATIC_CHART_DIR)
             if n.startswith("probe")],
            [],
            msg="inline mode wrote a PNG to disk",
        )

    def test_chart_mode_defaults_to_inline_on_vercel(self):
        """The platform-sensitive default must not need an environment variable."""
        script = (
            "from backend import charts\n"
            "print('inline' if charts.INLINE_CHARTS else 'file')\n"
        )
        for env in ({"VERCEL": "1"}, {"VERCEL": "true"}):
            envvars = dict(os.environ, **env)
            envvars.pop("CHART_MODE", None)
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=resume_app.BASE_DIR,
                env=envvars,
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(completed.stdout.strip(), "inline", msg=env)

        # An explicit setting still wins over the platform default.
        envvars = dict(os.environ, VERCEL="1", CHART_MODE="file")
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=resume_app.BASE_DIR,
            env=envvars,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(completed.stdout.strip(), "file")

    def test_unknown_chart_mode_falls_back_to_files(self):
        """A typo in CHART_MODE must not silently switch storage strategy."""
        script = (
            "from backend import charts\n"
            "print('inline' if charts.INLINE_CHARTS else 'file')\n"
        )
        for value in ("inline", "INLINE", " inline "):
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=resume_app.BASE_DIR,
                env=dict(os.environ, CHART_MODE=value),
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(completed.stdout.strip(), "inline", msg=value)

        for value in ("file", "", "base64", "inline-but-not-really"):
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=resume_app.BASE_DIR,
                env=dict(os.environ, CHART_MODE=value),
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(completed.stdout.strip(), "file", msg=value)


if __name__ == "__main__":
    unittest.main()