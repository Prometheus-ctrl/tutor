import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import tutor_validator  # noqa: E402


class TutorValidatorTest(unittest.TestCase):
    def test_gap_check_must_not_ask_or_advise(self):
        self.assertEqual(tutor_validator.validate("gap_check", "- 未覆盖：排除栈"), [])
        self.assertIn("gap_check_question", tutor_validator.validate("gap_check", "你确定吗？"))
        self.assertIn("gap_check_advice", tutor_validator.validate("gap_check", "你应该补上排除栈"))

    def test_guide_one_question(self):
        self.assertEqual(tutor_validator.validate("guide", "先说说 2 后面那段是什么？"), [])
        self.assertIn("guide_multi_question", tutor_validator.validate("guide", "是什么？为什么？"))

    def test_summary_no_question_or_mastery(self):
        self.assertEqual(tutor_validator.validate("summary", "你说到 FIFO，下一步补排除栈。"), [])
        self.assertIn("summary_question", tutor_validator.validate("summary", "你还有哪没说到？"))
        self.assertIn("summary_mastery", tutor_validator.validate("summary", "你已经掌握了。"))

    def test_clean_removes_summary_mastery(self):
        cleaned = tutor_validator.clean("summary", "你已经掌握了，继续。")
        self.assertNotIn("掌握", cleaned)
        self.assertIn("继续", cleaned)


if __name__ == "__main__":
    unittest.main()
