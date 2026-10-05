"""
Tests for PDF extraction, text cleaning and section detection.
"""

import unittest

from tests.helpers import (
    SAMPLE_RESUME,
    build_pdf,
    corrupted_pdf,
    empty_pdf,
    not_a_pdf,
    sample_pdf_bytes,
)

from backend.resume_parser import (
    EmptyPDFError,
    InvalidPDFError,
    _is_heading_line,
    clean_text,
    compute_metrics,
    detect_sections,
    extract_bullet_items,
    extract_contact,
    extract_education,
    extract_experience,
    parse_resume,
    preprocess,
)


class TestPDFExtraction(unittest.TestCase):
    """PDF reading must work and must fail gracefully."""

    def test_extracts_text_from_valid_pdf(self):
        from backend.resume_parser import extract_text_from_pdf

        text, pages = extract_text_from_pdf(sample_pdf_bytes())
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 200)
        self.assertEqual(pages, 1)
        self.assertIn("John Doe", text)

    def test_rejects_empty_upload(self):
        with self.assertRaises(EmptyPDFError):
            from backend.resume_parser import extract_text_from_pdf

            extract_text_from_pdf(b"")

    def test_rejects_non_pdf_content(self):
        from backend.resume_parser import extract_text_from_pdf

        with self.assertRaises(InvalidPDFError):
            extract_text_from_pdf(not_a_pdf())

    def test_rejects_corrupted_pdf(self):
        from backend.resume_parser import extract_text_from_pdf

        with self.assertRaises((InvalidPDFError, EmptyPDFError)):
            extract_text_from_pdf(corrupted_pdf())

    def test_rejects_pdf_without_text_layer(self):
        from backend.resume_parser import extract_text_from_pdf

        with self.assertRaises(EmptyPDFError):
            extract_text_from_pdf(empty_pdf())

    def test_multi_page_pdf_reports_page_count(self):
        long_text = SAMPLE_RESUME + "\n" + ("Extra page content line\n" * 80)
        from backend.resume_parser import extract_text_from_pdf

        _text, pages = extract_text_from_pdf(build_pdf(long_text))
        self.assertGreaterEqual(pages, 2)


class TestTextCleaning(unittest.TestCase):
    def test_normalises_bullets_and_smart_quotes(self):
        messy = "\u2022 First item \u2018quoted\u2019\n\u2013 second"
        cleaned = clean_text(messy)
        self.assertIn("- First item", cleaned)
        self.assertIn("'quoted'", cleaned)
        self.assertNotIn("\u2022", cleaned)

    def test_collapses_repeated_blank_lines(self):
        self.assertNotIn("\n\n\n", clean_text("a\n\n\n\n\nb"))

    def test_dehyphenates_words_split_across_lines(self):
        self.assertIn("development", clean_text("devel-\nopment"))

    def test_preprocess_removes_stop_words_and_lowercases(self):
        tokens = preprocess("The quick brown fox and the lazy dog")
        self.assertIn("quick", tokens)
        self.assertNotIn("the", tokens)
        self.assertNotIn("and", tokens)

    def test_metrics_are_computed(self):
        metrics = compute_metrics("Python developer.\nBuilt an app.\n", pages=1)
        self.assertGreater(metrics["word_count"], 0)
        self.assertEqual(metrics["pages"], 1.0)
        self.assertIn("special_char_ratio", metrics)


class TestSectionDetection(unittest.TestCase):
    def test_detects_all_sections_of_the_sample(self):
        detected, bodies = detect_sections(clean_text(SAMPLE_RESUME))
        for expected in ("summary", "education", "skills", "experience",
                         "projects", "certifications", "achievements",
                         "languages", "interests"):
            self.assertIn(expected, detected)

        # Section bodies hold the content that follows the heading.
        self.assertIn("Python", bodies["skills"])
        self.assertIn("Chandigarh University", bodies["education"])
        self.assertIn("Tech Solutions", bodies["experience"])
        # A heading is never repeated inside its own body.
        for key, body in bodies.items():
            self.assertFalse(body.strip().upper().startswith(key.upper()))

    def test_missing_sections_are_reported_not_fatal(self):
        minimal = """Anita Sharma
anita.sharma@example.com

Skills
Python, SQL, Pandas
"""
        detected, _bodies = detect_sections(minimal)
        self.assertIn("skills", detected)
        self.assertNotIn("experience", detected)

    def test_all_caps_headings_are_detected(self):
        text = "NAME\n\nTECHNICAL SKILLS\nPython, SQL\n\nWORK EXPERIENCE\nIntern"
        detected, _ = detect_sections(text)
        self.assertIn("skills", detected)
        self.assertIn("experience", detected)

    def test_sentences_are_not_mistaken_for_headings(self):
        text = "I am looking for a job in the software industry.\n\nSkills\nPython"
        detected, _ = detect_sections(text)
        self.assertEqual(detected, ["skills"])


class TestFieldExtraction(unittest.TestCase):
    def setUp(self):
        self.resume = parse_resume(sample_pdf_bytes())

    def test_contact_details(self):
        contact = self.resume.contact
        self.assertEqual(contact.name, "John Doe")
        self.assertIn("john.doe@example.com", contact.emails)
        self.assertTrue(contact.phones)
        self.assertTrue(any("linkedin" in link for link in contact.links))
        self.assertTrue(any("github" in link for link in contact.links))

    def test_contact_completeness_is_percentage(self):
        self.assertGreaterEqual(self.resume.contact.completeness, 75)
        self.assertLessEqual(self.resume.contact.completeness, 100)

    def test_education_fields(self):
        self.assertTrue(self.resume.education)
        entry = self.resume.education[0]
        self.assertIn("BCA", entry.degree)
        self.assertIn("University", entry.institution)
        self.assertEqual(entry.year, "2024")
        self.assertIn("CGPA", entry.score)

    def test_experience_fields(self):
        self.assertTrue(self.resume.experience)
        entry = self.resume.experience[0]
        self.assertIn("Intern", entry.title)
        self.assertIn("Tech Solutions", entry.organisation)
        self.assertIn("2024", entry.duration)

    def test_projects_detected(self):
        self.assertGreaterEqual(len(self.resume.projects), 2)
        names = " ".join(p.name for p in self.resume.projects)
        self.assertIn("AI Resume Checker", names)

    def test_certifications_detected(self):
        self.assertGreaterEqual(len(self.resume.certifications), 2)
        self.assertIn("PL/SQL", " ".join(c.name for c in self.resume.certifications))

    def test_languages_and_interests(self):
        self.assertIn("English", self.resume.languages_listed)
        self.assertTrue(self.resume.interests)

    def test_missing_sections_list(self):
        self.assertIn("summary", self.resume.sections_found)
        self.assertTrue(all(
            key not in self.resume.sections_found for key in self.resume.sections_missing
        ))

    def test_helpers_work_on_plain_text(self):
        education = extract_education("B.Tech Computer Science, XYZ Institute, 2021, CGPA 8.1")
        self.assertTrue(education)
        experience = extract_experience("Data Analyst, ABC Ltd - 2022 to 2023")
        self.assertTrue(experience)


class TestBulletItemExtraction(unittest.TestCase):
    """
    Content lists must contain real content, not stray section headings.

    A resume that writes "ACHIEVEMENTS AND PROJECTS" on one line would
    otherwise have that heading reported back to the user as an achievement.
    """

    def test_heading_lines_are_recognised(self):
        headings = [
            "ACHIEVEMENTS AND PROJECTS",
            "ACHIEVEMENTS & PROJECTS",
            "CERTIFICATIONS",
            "Technical Skills:",
            "EDUCATION",
            "Languages",
            "INTERESTS AND HOBBIES",
            "Work Experience",
            "References",
        ]
        for line in headings:
            with self.subTest(line=line):
                self.assertTrue(_is_heading_line(line))

    def test_real_content_is_not_mistaken_for_a_heading(self):
        content = [
            "Winner, Smart India Hackathon 2024 regional round.",
            "AWS Certified Cloud Practitioner (2025)",
            "Published 6 technical articles on backend engineering.",
            "Improved keyword extraction accuracy by 35% across 120 resumes.",
            "Available on request",
        ]
        for line in content:
            with self.subTest(line=line):
                self.assertFalse(_is_heading_line(line))

    def test_inline_headings_are_dropped(self):
        body = (
            "ACHIEVEMENTS AND PROJECTS\n"
            "Winner, Smart India Hackathon 2024 regional round.\n"
            "REFERENCES\n"
            "Available on request\n"
        )
        items = extract_bullet_items(body)
        self.assertEqual(
            items,
            [
                "Winner, Smart India Hackathon 2024 regional round.",
                "Available on request",
            ],
        )

    def test_no_heading_survives_into_parsed_sections(self):
        resume = parse_resume(sample_pdf_bytes())
        parsed = list(resume.achievements)
        parsed += [entry.name for entry in resume.certifications]
        parsed += [entry.name for entry in resume.projects]
        self.assertTrue(parsed, "sample resume should yield some parsed content")
        for text in parsed:
            self.assertFalse(
                _is_heading_line(text),
                msg=f"parsed content still contains the heading {text!r}",
            )


if __name__ == "__main__":
    unittest.main()