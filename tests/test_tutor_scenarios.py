import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import tutor_scenarios  # noqa: E402


class TutorScenarioTest(unittest.TestCase):
    def test_all_subject_situation_combinations(self):
        for subject in tutor_scenarios.SUBJECTS:
            for situation in tutor_scenarios.SITUATIONS:
                p = tutor_scenarios.policy_for(subject, situation)
                self.assertEqual(p["subject"], subject)
                self.assertEqual(p["situation"], situation)
                self.assertTrue(p["focus"])
                self.assertTrue(p["must"])
                self.assertTrue(p["avoid"])
                self.assertIn(p["action"], ("probe", "hint", "explain", "check", "advance", "redirect"))

    def test_subject_probe_budgets(self):
        self.assertEqual(tutor_scenarios.policy_for("math2", "answer_only")["max_probes"], 1)
        self.assertEqual(tutor_scenarios.policy_for("english2", "answer_only")["max_probes"], 1)
        self.assertEqual(tutor_scenarios.policy_for("cs408", "answer_only")["max_probes"], 1)
        self.assertEqual(tutor_scenarios.policy_for("writing", "answer_only")["max_probes"], 0)

    def test_hard_situations_never_probe(self):
        for subject in tutor_scenarios.SUBJECTS:
            for situation in ("stuck", "frustration", "off_topic"):
                p = tutor_scenarios.policy_for(subject, situation)
                self.assertNotEqual(p["action"], "probe")
                self.assertEqual(p["max_probes"], 0)

    def test_fake_understanding_is_check(self):
        self.assertEqual(tutor_scenarios.policy_for("cs408", "fake_understanding")["action"], "check")

    def test_exam_mode_never_probes(self):
        self.assertEqual(tutor_scenarios.policy_for("math2", "exam")["max_probes"], 0)
        self.assertEqual(tutor_scenarios.policy_for("math2", "exam")["action"], "hint")

    def test_mode_overrides_move(self):
        self.assertEqual(tutor_scenarios.situation_for("answer", "review"), "review")
        self.assertEqual(tutor_scenarios.situation_for("answer", "exam"), "exam")
        self.assertEqual(tutor_scenarios.situation_for("stuck", "tutor"), "stuck")
        self.assertEqual(tutor_scenarios.situation_for("frustration", "tutor"), "frustration")


if __name__ == "__main__":
    unittest.main()
