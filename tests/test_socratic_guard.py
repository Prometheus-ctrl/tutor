import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import tutor_server  # noqa: E402


class SocraticGuardTest(unittest.TestCase):
    def test_question_streak_counts_trailing_questions(self):
        history = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "依据是什么？"},
            {"role": "user", "content": "b"},
            {"role": "assistant", "content": "为什么？"},
        ]
        self.assertEqual(tutor_server._question_streak(history), 2)

    def test_force_hint_uses_lesson_plan(self):
        plan = {"stuck": [{"hint": "谁先写谁先出", "next": "列出三个数据"}]}
        text = tutor_server._force_hint(plan, "进行不下去了")
        self.assertIn("谁先写谁先出", text)
        self.assertIn("列出三个数据", text)
        self.assertNotIn("？", text)

    def test_force_hint_uses_ladder_level(self):
        plan = {
            "hint_ladder": [
                {"level": 1, "cue": "先看依次"},
                {"level": 2, "cue": "先写进去的先取出来"},
            ],
            "stuck": [{"next": "列出前三个数据"}],
        }
        text = tutor_server._force_hint(plan, "还是不会", 1)
        self.assertIn("先写进去的先取出来", text)
        self.assertIn("列出前三个数据", text)

    def test_force_hint_pauses_after_three_levels(self):
        plan = {"hint_ladder": [{"level": 1, "cue": "线索"}]}
        text = tutor_server._force_hint(plan, "还是不会", 3)
        self.assertIn("三级提示", text)
        self.assertIn("换一道", text)
        self.assertNotIn("线索", text)

    def test_normal_analysis_is_not_forced_by_question_streak(self):
        history = [
            {"role": "assistant", "content": "根在哪？"},
            {"role": "user", "content": "根是 1"},
            {"role": "assistant", "content": "左子树整段是谁？"},
            {"role": "user", "content": "是 7,5,6,2,4"},
        ]
        self.assertGreaterEqual(tutor_server._question_streak(history), 2)
        self.assertFalse(tutor_server._should_force("二是子树的根，756 是一个子树", {}, "reason"))

    def test_distress_or_over_budget_forces(self):
        self.assertTrue(tutor_server._should_force("进行不下去了", {}, "stuck"))
        self.assertTrue(tutor_server._should_force("选 B", {"over_budget": True}, "answer"))
        self.assertFalse(tutor_server._should_force("因为先入先出", {"over_budget": True}, "reason"))


if __name__ == "__main__":
    unittest.main()
