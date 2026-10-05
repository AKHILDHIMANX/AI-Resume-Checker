"""
Tests for the ATS analyzer and the weighted scoring engine.
"""

import unittest

from tests.helpers import SAMPLE_RESUME, NO_SKILLS_RESUME

from backend.ats_analyzer import DISCLAIMER, MAX_POINTS, analyze_ats, ats_score_breakdown
from backend.resume_parser import clean_text, compute_metrics, detect_sections, parse_resume
from backend.skill_extractor import extract_skills
from backend.resume_parser import ParsedResume
from backend.scoring import (
    OVERALL_WEIGHTS,
    calculate_scores,
    grade_for,
    missing_section_labels,
    score_content,
    score_skills,
    score_structure,
)


def build_resume(text):
    """Parse free text into a ParsedResume without touching the filesystem."""
    clean = clean_text(text)
    detected, bodies = detect_sections(clean)
    resume = ParsedResume(raw_text=clean, clean_text=clean, pages=1)
    resume.word_count = len(clean.split())
    resume.char_count = len(clean)
    resume.metrics = compute_metrics(clean, 1)
    resume.contact = __import__(
        "backend.resume_parser", fromlist=["extract_contact"]
    ).extract_contact(clean)
    resume.sections_found = detected
    resume.section_text = bodies
    return resume


class TestATSAnalyzer(unittest.TestCase):
    def setUp(self):
        self.resume = build_resume(SAMPLE_RESUME)
        self.skills = extract_skills(SAMPLE_RESUME).technical

    def test_score_within_range(self):
        report = analyze_ats(self.resume, self.skills)
        self.assertGreaterEqual(report.score, 0)
        self.assertLessEqual(report.score, 100)

    def test_all_checks_present_and_sum_to_score(self):
        report = analyze_ats(self.resume, self.skills)
        self.assertEqual(len(report.checks), len(MAX_POINTS))
        total = sum(check.score for check in report.checks)
        self.assertAlmostEqual(total, report.score, places=6)
        self.assertEqual(sum(MAX_POINTS.values()), 100)

    def test_no_check_exceeds_its_maximum(self):
        for check in analyze_ats(self.resume, self.skills).checks:
            self.assertLessEqual(check.score, check.max_score)

    def test_disclaimer_is_disclaimer(self):
        report = analyze_ats(self.resume, self.skills)
        self.assertIn("does not", report.disclaimer.lower())
        self.assertIn("estimate", report.disclaimer.lower())
        self.assertEqual(report.disclaimer, DISCLAIMER)

    def test_missing_sections_are_reported_as_issues(self):
        minimal = build_resume("Anita Sharma\nanita@example.com\n\nSKILLS\nPython, SQL")
        report = analyze_ats(minimal, ["Python", "SQL"])
        joined = " ".join(report.issues).lower()
        self.assertIn("experience", joined)
        self.assertIn("education", joined)

    def test_good_resume_scores_higher_than_poor_resume(self):
        good = analyze_ats(self.resume, self.skills).score
        poor_resume = build_resume(NO_SKILLS_RESUME)
        poor = analyze_ats(poor_resume, []).score
        self.assertGreater(good, poor)

    def test_breakdown_helper_returns_serialisable_dict(self):
        breakdown = ats_score_breakdown(self.resume, self.skills)
        self.assertIn("score", breakdown)
        self.assertIsInstance(breakdown["checks"], list)


class TestScoring(unittest.TestCase):
    def setUp(self):
        self.resume = build_resume(SAMPLE_RESUME)
        self.profile = extract_skills(SAMPLE_RESUME)

    def test_overall_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(OVERALL_WEIGHTS.values()), 1.0, places=6)

    def test_component_scores_in_range(self):
        for component in (
            score_structure(self.resume),
            score_content(self.resume, self.profile),
            score_skills(self.profile, self.resume),
        ):
            self.assertGreaterEqual(component.score, 0)
            self.assertLessEqual(component.score, 100)
            self.assertTrue(component.breakdown)

    def test_overall_is_weighted_sum_of_components(self):
        ats_score = 80.0
        report = calculate_scores(self.resume, self.profile, ats_score)
        manual = sum(c.score * c.weight for c in report.components)
        self.assertAlmostEqual(report.overall, manual, places=6)
        self.assertEqual(len(report.components), 4)

    def test_scores_are_deterministic(self):
        first = calculate_scores(self.resume, self.profile, 75.0).overall
        second = calculate_scores(self.resume, self.profile, 75.0).overall
        self.assertEqual(first, second)

    def test_better_resume_scores_higher(self):
        good = calculate_scores(self.resume, self.profile, 90).overall
        poor_resume = build_resume(NO_SKILLS_RESUME)
        poor_profile = extract_skills(NO_SKILLS_RESUME)
        poor = calculate_scores(poor_resume, poor_profile, 30).overall
        self.assertGreater(good, poor)

    def test_grading_bands(self):
        self.assertEqual(grade_for(95), "Excellent")
        self.assertEqual(grade_for(85), "Very Good")
        self.assertEqual(grade_for(72), "Good")
        self.assertEqual(grade_for(62), "Needs Improvement")
        self.assertEqual(grade_for(45), "Weak")
        self.assertEqual(grade_for(10), "Very Weak")

    def test_missing_section_labels(self):
        minimal = build_resume("Anita Sharma\nanita@example.com\n\nSKILLS\nPython")
        labels = missing_section_labels(minimal)
        keys = {item["key"] for item in labels}
        self.assertIn("education", keys)
        self.assertIn("experience", keys)
        self.assertTrue(all(item["reason"] for item in labels))

    def test_missing_sections_empty_for_complete_resume(self):
        self.assertEqual(missing_section_labels(self.resume), [])


if __name__ == "__main__":
    unittest.main()