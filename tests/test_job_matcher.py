"""
Tests for job role matching (weighted coverage + TF-IDF cosine similarity).
"""

import unittest

from tests.helpers import SAMPLE_RESUME, NO_SKILLS_RESUME

from backend.job_matcher import (
    UnknownRoleError,
    _dedupe_across_buckets,
    _dedupe_role_skills,
    _normalise_skill_name,
    get_role,
    list_roles,
    match_job,
    normalise_role,
    rank_roles,
    score_skill_coverage,
    text_similarity,
)

PYTHON_RESUME = """
Skills: Python, Flask, Django, SQL, MySQL, PostgreSQL, Git, GitHub, Linux,
Pandas, NumPy, Docker, REST API, Data Structures, Algorithms, Unit Testing,
AWS, CI/CD, Redis.
Projects: built REST APIs with Flask and deployed on AWS using Docker and
Jenkins CI/CD pipelines. Wrote unit tests and used Git for version control.
"""

EMPTY_RESUME = "Nothing relevant here at all."


class TestRoleDataset(unittest.TestCase):
    def test_ten_roles_available(self):
        roles = list_roles()
        self.assertGreaterEqual(len(roles), 10)
        names = [role["role"] for role in roles]
        for expected in ("Python Developer", "Data Analyst", "DevOps Engineer",
                         "Cybersecurity Analyst", "Full Stack Developer"):
            self.assertIn(expected, names)

    def test_role_lookup_is_case_insensitive(self):
        self.assertEqual(normalise_role("python developer"), "Python Developer")
        self.assertEqual(normalise_role("  DATA ANALYST "), "Data Analyst")

    def test_alias_resolution(self):
        self.assertEqual(normalise_role("ml engineer"), "Machine Learning Engineer")
        self.assertEqual(normalise_role("sde"), "Software Developer")

    def test_unknown_role_raises(self):
        with self.assertRaises(UnknownRoleError):
            normalise_role("Astronaut Trainer")

    def test_empty_role_raises(self):
        with self.assertRaises(UnknownRoleError):
            normalise_role("   ")

    def test_get_role_returns_definition(self):
        role = get_role("Python Developer")
        self.assertIn("Python", role["core_skills"])
        self.assertIn("summary", role)


class TestSkillCoverage(unittest.TestCase):
    def test_full_coverage_is_high(self):
        role = get_role("Python Developer")
        score = score_skill_coverage(PYTHON_RESUME, role)["score"]
        self.assertGreater(score, 50)

    def test_empty_resume_scores_zero(self):
        role = get_role("Python Developer")
        self.assertEqual(score_skill_coverage(EMPTY_RESUME, role)["score"], 0)

    def test_coverage_never_exceeds_100(self):
        role = get_role("Python Developer")
        everything = " ".join(
            role["core_skills"] + role["preferred_skills"] + role["bonus_skills"]
        )
        self.assertLessEqual(score_skill_coverage(everything, role)["score"], 100)

    def test_core_and_missing_are_separated(self):
        role = get_role("Python Developer")
        result = score_skill_coverage(PYTHON_RESUME, role)
        self.assertIn("Python", result["core_matched"])
        self.assertNotIn("Python", result["core_missing"])


class TestTextSimilarity(unittest.TestCase):
    def test_similarity_is_percentage(self):
        score = text_similarity(PYTHON_RESUME, "Python Developer")
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_relevant_resume_scores_above_unrelated(self):
        relevant = text_similarity(PYTHON_RESUME, "Python Developer")
        unrelated = text_similarity(EMPTY_RESUME, "Python Developer")
        self.assertGreater(relevant, unrelated)

    def test_empty_resume_gives_zero(self):
        self.assertEqual(text_similarity("", "Python Developer"), 0)


class TestMatchJob(unittest.TestCase):
    def test_matched_and_missing_lists(self):
        """A partial resume produces both a matched list and a missing list."""
        partial = "Skills: Python, Flask, MySQL and Git. Built REST APIs."
        result = match_job(partial, "Python Developer")
        self.assertIn("Python", result.matched_core)
        self.assertIn("Django", result.missing_core)
        self.assertTrue(result.missing_preferred or result.missing_bonus)
        self.assertEqual(result.role, "Python Developer")

    def test_matched_skills_have_no_duplicates(self):
        result = match_job(PYTHON_RESUME, "Python Developer")
        self.assertEqual(len(result.matched_skills), len(set(result.matched_skills)))
        for bucket in (result.matched_core, result.matched_preferred, result.matched_bonus):
            self.assertEqual(len(bucket), len(set(bucket)))

    def test_role_skills_are_not_double_counted(self):
        """Every skill must count once, in exactly one importance tier."""
        role = get_role("Python Developer")
        raw = role["core_skills"] + role["preferred_skills"] + role["bonus_skills"]
        normalised = [_normalise_skill_name(s) for s in raw]
        deduped = [_normalise_skill_name(s) for s in _dedupe_role_skills(raw)]
        self.assertEqual(len(deduped), len(set(normalised)))

        cleaned = _dedupe_across_buckets({
            "core": list(role["core_skills"]),
            "preferred": list(role["preferred_skills"]),
            "bonus": list(role["bonus_skills"]),
        })
        across = ([_normalise_skill_name(s) for s in cleaned["core"]] +
                  [_normalise_skill_name(s) for s in cleaned["preferred"]] +
                  [_normalise_skill_name(s) for s in cleaned["bonus"]])
        self.assertEqual(len(across), len(set(across)))

    def test_missing_skills_have_no_duplicates(self):
        """The reported gap list must never repeat a skill."""
        for role in list_roles():
            result = match_job(PYTHON_RESUME, role["role"])
            missing = (result.missing_core + result.missing_preferred
                       + result.missing_bonus)
            self.assertEqual(
                len(missing), len(set(missing)),
                msg=f"{role['role']} repeats a missing skill: {missing}",
            )
            self.assertEqual(
                len(result.matched_skills), len(set(result.matched_skills)),
                msg=f"{role['role']} repeats a matched skill: {result.matched_skills}",
            )
            self.assertFalse(
                set(result.matched_skills) & set(missing),
                msg=f"{role['role']} reports a skill as both matched and missing",
            )

    def test_cross_tier_duplicate_is_kept_in_highest_tier(self):
        """A skill listed as core and bonus survives only as core."""
        cleaned = _dedupe_across_buckets({
            "core": ["Python", "REST API"],
            "preferred": ["REST API", "Git"],
            "bonus": ["REST API", "Docker"],
        })
        self.assertIn("REST API", cleaned["core"])
        self.assertNotIn("REST API", cleaned["preferred"])
        self.assertNotIn("REST API", cleaned["bonus"])
        self.assertEqual(
            cleaned["core"] + cleaned["preferred"] + cleaned["bonus"],
            ["Python", "REST API", "Git", "Docker"],
        )

    def test_score_within_range_and_blend(self):
        result = match_job(PYTHON_RESUME, "Python Developer")
        self.assertGreaterEqual(result.match_score, 0)
        self.assertLessEqual(result.match_score, 100)
        expected = round(
            0.65 * result.skill_coverage_score + 0.35 * result.text_similarity_score, 1
        )
        self.assertAlmostEqual(result.match_score, expected, places=1)

    def test_result_is_json_serialisable(self):
        import json

        payload = match_job(PYTHON_RESUME, "Data Analyst").to_dict()
        json.dumps(payload)
        for key in ("role", "match_score", "matched_skills", "missing_skills",
                    "skill_coverage_score", "text_similarity_score"):
            self.assertIn(key, payload)

    def test_unknown_role_raises(self):
        with self.assertRaises(UnknownRoleError):
            match_job(PYTHON_RESUME, "Underwater Basket Weaver")

    def test_explanation_is_not_a_hiring_claim(self):
        """The score text must present similarity only, never a verdict."""
        result = match_job(PYTHON_RESUME, "Python Developer")
        lowered = result.explanation.lower()
        self.assertIn("similarity", lowered)
        self.assertIn("not a judgement", lowered)
        for forbidden in ("you are qualified", "suitable for the role",
                          "recommended for hire", "unqualified"):
            self.assertNotIn(forbidden, lowered)

    def test_skillless_resume_matches_nothing(self):
        result = match_job(NO_SKILLS_RESUME, "Data Scientist")
        self.assertEqual(result.matched_skills, [])
        self.assertLess(result.match_score, 20)

    def test_different_roles_produce_different_scores(self):
        python = match_job(SAMPLE_RESUME, "Python Developer").match_score
        security = match_job(SAMPLE_RESUME, "Cybersecurity Analyst").match_score
        self.assertNotEqual(python, security)


class TestRankRoles(unittest.TestCase):
    def test_ranks_are_sorted_descending(self):
        ranking = rank_roles(SAMPLE_RESUME, top_n=6)
        self.assertTrue(ranking)
        scores = [item["score"] for item in ranking]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_returns_requested_number_of_roles(self):
        self.assertEqual(len(rank_roles(SAMPLE_RESUME, top_n=3)), 3)

    def test_default_ranks_every_role_in_the_dataset(self):
        """
        The dashboard says "compared with every role", so the ranking must not
        silently truncate the dataset.
        """
        ranking = rank_roles(SAMPLE_RESUME)
        self.assertEqual(len(ranking), len(list_roles()))
        self.assertEqual(
            {item["role"] for item in ranking},
            {item["role"] for item in list_roles()},
        )

    def test_every_ranked_role_carries_its_breakdown(self):
        for item in rank_roles(SAMPLE_RESUME):
            with self.subTest(role=item["role"]):
                self.assertIn("skill_coverage", item)
                self.assertIn("text_similarity", item)
                self.assertTrue(item["category"])
                self.assertGreaterEqual(item["score"], 0.0)
                self.assertLessEqual(item["score"], 100.0)


if __name__ == "__main__":
    unittest.main()