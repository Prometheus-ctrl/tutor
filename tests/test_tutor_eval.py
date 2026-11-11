import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import tutor_eval  # noqa: E402


class TutorEvalTest(unittest.TestCase):
    def test_evaluate_counts_actual_and_simulated(self):
        turns = [
            {"role": "user", "content": "选 B"},
            {"role": "assistant", "content": "依据是什么？"},
            {"role": "user", "content": "先入先出"},
            {"role": "assistant", "content": "那为什么不是栈？"},
        ]
        data = tutor_eval.evaluate(turns)
        self.assertEqual(data["user_turns"], 2)
        self.assertEqual(data["assistant_turns"], 2)
        self.assertEqual(data["actual_question_turns"], 2)
        self.assertEqual(data["actual_max_question_streak"], 2)
        self.assertEqual(data["simulated_actions"][0]["action"], "probe")
        self.assertEqual(data["simulated_actions"][1]["action"], "advance")

    def test_style_flags_counted(self):
        turns = [
            {"role": "user", "content": "不会"},
            {"role": "assistant", "content": "太棒了！再想想。"},
        ]
        data = tutor_eval.evaluate(turns)
        self.assertEqual(data["style_flags"].get("praise"), 1)
        self.assertEqual(data["style_flags"].get("vague"), 1)


if __name__ == "__main__":
    unittest.main()
