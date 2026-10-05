"""
Tests for technical / soft skill detection, keywords and content signals.
"""

import unittest

from tests.helpers import SAMPLE_RESUME

from backend.skill_data import load_skill_data, soft_skills, technical_skills
from backend.skill_extractor import (
    count_filler_phrases,
    count_quantifiers,
    extract_skills,
    find_action_verbs,
    find_alias_skills,
    find_soft_skills,
    find_technical_skills,
)


class TestSkillDataset(unittest.TestCase):
    def test_dataset_loads(self):
        data = load_skill_data()
        self.assertIn("categories", data)
        self.assertIn("soft_skills", data)

    def test_expected_categories_exist(self):
        categories = technical_skills()
        for name in ("Programming", "Web", "Data", "Database", "Tools",
                     "Cloud / DevOps"):
            self.assertIn(name, categories)

    def test_brief_says_python_is_present(self):
        self.assertIn("Python", technical_skills()["Programming"])

    def test_soft_skills_not_empty(self):
        self.assertGreater(len(soft_skills()), 5)


class TestTechnicalSkillDetection(unittest.TestCase):
    def setUp(self):
        self.text = SAMPLE_RESUME

    def test_detects_skills_by_category(self):
        found = find_technical_skills(self.text)
        self.assertIn("Python", found["Programming"])
        self.assertIn("Java", found["Programming"])
        self.assertIn("Flask", found["Web"])
        self.assertIn("Pandas", found["Data"])
        self.assertIn("MySQL", found["Database"])
        self.assertIn("Git", found["Tools"])

    def test_detects_named_libraries(self):
        found = find_technical_skills(self.text)
        flat = [s for skills in found.values() for s in skills]
        for skill in ("NumPy", "Matplotlib", "Docker", "Oracle", "MongoDB"):
            self.assertIn(skill, flat)

    def test_word_boundary_protection(self):
        """'C' must not match inside 'C++', and 'Java' not inside 'JavaScript'."""
        found = find_technical_skills("Skilled in C++, C# and JavaScript only")
        flat = [s for skills in found.values() for s in skills]
        self.assertIn("C++", flat)
        self.assertIn("C#", flat)
        self.assertNotIn("C", flat)
        self.assertIn("JavaScript", flat)
        self.assertNotIn("Java", flat)

    def test_requires_word_boundary_not_substring(self):
        found = find_technical_skills("I enjoy painting and drawing classes")
        flat = [s for skills in found.values() for s in skills]
        self.assertNotIn("R", flat)
        self.assertNotIn("Go", flat)

    def test_empty_text_returns_nothing(self):
        self.assertEqual(find_technical_skills(""), {})

    def test_alias_detection(self):
        """'sklearn' is reported as the alias used for 'Scikit Learn'."""
        aliases = find_alias_skills("Used sklearn, postgres and js daily")
        names = [item["canonical"] for item in aliases]
        self.assertIn("Scikit Learn", names)
        self.assertIn("PostgreSQL", names)
        self.assertIn("JavaScript", names)

    def test_alias_not_reported_when_canonical_word_present(self):
        """A skill written in full must not also appear as an alias hit."""
        aliases = find_alias_skills("Built with Scikit Learn and JavaScript")
        names = [item["canonical"] for item in aliases]
        self.assertNotIn("Scikit Learn", names)
        self.assertNotIn("JavaScript", names)

    def test_alias_hit_records_the_matched_alias(self):
        aliases = find_alias_skills("Used sklearn daily")
        entry = next(item for item in aliases if item["canonical"] == "Scikit Learn")
        self.assertEqual(entry["alias"], "sklearn")

    def test_no_aliases_returns_empty(self):
        self.assertEqual(find_alias_skills("Python SQL MySQL"), [])


class TestSoftSkillDetection(unittest.TestCase):
    def test_detects_soft_skills(self):
        found = find_soft_skills(
            "Strong communication, teamwork and problem solving ability. "
            "Reliable time management and leadership in college events."
        )
        self.assertIn("Communication", found)
        self.assertIn("Teamwork", found)
        self.assertIn("Problem Solving", found)
        self.assertIn("Time Management", found)

    def test_no_soft_skills_returns_empty(self):
        self.assertEqual(find_soft_skills("Python SQL MySQL"), [])


class TestKeywordExtraction(unittest.TestCase):
    def test_keywords_are_returned_with_weights(self):
        profile = extract_skills(SAMPLE_RESUME)
        self.assertTrue(profile.keywords)
        keywords = profile.keywords
        self.assertIn("term", keywords[0])
        self.assertIn("score", keywords[0])
        self.assertGreater(keywords[0]["score"], 0)

    def test_keywords_are_ranked_descending(self):
        profile = extract_skills(SAMPLE_RESUME)
        scores = [k["score"] for k in profile.keywords]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_short_text_falls_back_to_frequency(self):
        profile = extract_skills("Python developer. Python is used for web development.")
        self.assertTrue(profile.keywords)
        self.assertIn("python", [k["term"] for k in profile.keywords])


class TestContentSignals(unittest.TestCase):
    def test_action_verbs_found(self):
        verbs = find_action_verbs(SAMPLE_RESUME)
        self.assertIn("developed", verbs)
        self.assertIn("built", verbs)

    def test_quantifiers_counted(self):
        # "40 SQL queries", "35 percent", "60 percent"
        self.assertGreaterEqual(count_quantifiers(SAMPLE_RESUME), 3)

    def test_quantifier_patterns(self):
        self.assertEqual(count_quantifiers("Reduced cost by 30%"), 1)
        self.assertEqual(count_quantifiers("Improved accuracy by 12 percent"), 1)
        self.assertEqual(count_quantifiers("Served 5000 requests per day"), 1)
        self.assertEqual(count_quantifiers("Budget was Rs. 25000 per month"), 1)
        self.assertEqual(count_quantifiers("Improved throughput 3x faster"), 1)
        self.assertEqual(count_quantifiers("No numbers in this sentence at all"), 0)

    def test_filler_phrases_counted(self):
        self.assertGreaterEqual(
            count_filler_phrases("Was responsible for various tasks and helped the team."),
            2,
        )


class TestSkillProfile(unittest.TestCase):
    def test_profile_has_all_parts(self):
        profile = extract_skills(SAMPLE_RESUME, {"skills": "Python, SQL"})
        self.assertTrue(profile.technical)
        self.assertTrue(profile.technical_by_category)
        self.assertTrue(profile.soft)
        self.assertGreater(profile.total_matches, 5)
        self.assertEqual(profile.skill_to_category["Python"], "Programming")

    def test_source_sections_recorded(self):
        profile = extract_skills(SAMPLE_RESUME, {"skills": "Python, SQL, Flask"})
        self.assertEqual(profile.source_sections.get("Python"), "skills")

    def test_category_counts(self):
        profile = extract_skills(SAMPLE_RESUME)
        counts = profile.category_counts
        self.assertIn("Programming", counts)
        self.assertGreater(counts["Programming"], 0)


if __name__ == "__main__":
    unittest.main()