import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import prompt_loader  # noqa: E402


class PromptLoaderTest(unittest.TestCase):
    def test_math_and_format(self):
        text = prompt_loader.compose("math2", "single", "tutor")
        self.assertIn("数二", text)
        self.assertIn("【显示】", text)
        self.assertIn("【朗读】", text)
        self.assertIn("学生只报选项", text)

    def test_english_reading_not_math(self):
        text = prompt_loader.compose("english2", "reading_set", "tutor")
        self.assertNotIn("数学题", text)
        self.assertIn("定位题干关键词", text)
        self.assertIn("干扰项", text)

    def test_unknown_falls_back(self):
        text = prompt_loader.compose("unknown", "unknown", "tutor")
        self.assertIn("通用", text)
        self.assertIn("不假设这是数学题", text)

    def test_review_mode(self):
        text = prompt_loader.compose("math2", "single", "review")
        self.assertIn("整题复述", text)
        self.assertIn("不主动提示", text)

    def test_exam_mode(self):
        text = prompt_loader.compose("math2", "single", "exam")
        self.assertIn("考试模式", text)
        self.assertIn("只给最小提示", text)

    def test_no_question_for_question_sake(self):
        text = prompt_loader.compose("cs408", "cs_choice", "tutor")
        self.assertIn("不要为了问而问", text)
        self.assertIn("只有答案会影响下一步时，才问", text)

    def test_role_modes_compose(self):
        self.assertIn("一次只补一个缺口", prompt_loader.compose("math2", "single", "gap_fill"))
        self.assertIn("一次只问一个问题", prompt_loader.compose("math2", "single", "guide"))
        self.assertIn("你说到的点", prompt_loader.compose("math2", "single", "summary"))


if __name__ == "__main__":
    unittest.main()
