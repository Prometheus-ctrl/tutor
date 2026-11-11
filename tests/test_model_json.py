# -*- coding: utf-8 -*-
"""模型 JSON 解析回归：LaTeX 反斜杠没转义时不能把原始 JSON 当总结。"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import speech  # noqa: E402

# 真实故障样本：公式分隔符 \( \) 没转义，LaTeX 命令又转义成了 \\frac，直接 json.loads 会失败。
BROKEN = (
    '思路：{"outline":"1. 求导得切线斜率 \\( k=(\\\\arctan x)\'|_{x=1}=\\\\frac{1}{1+1^2} \\)；'
    '2. 求切点纵坐标 \\( y_0=\\\\arctan 1=\\\\frac{\\\\pi}{4} \\)。",'
    '"stuck":"反三角函数导数公式遗忘：\\( (\\\\arctan x)\'=\\\\frac{1}{1+x^2} \\)。",'
    '"pitfalls":"法线斜率是负倒数 \\( -\\\\frac{1}{k} \\)。",'
    '"suggested":"hard","reason":"关键公式需要提示。"}'
)


class ParseModelJsonTest(unittest.TestCase):
    def test_repairs_unescaped_latex(self):
        obj = speech.parse_model_json(BROKEN)
        self.assertIsInstance(obj, dict)
        self.assertEqual(obj["suggested"], "hard")
        self.assertIn("\\frac{1}{1+1^2}", obj["outline"])
        self.assertIn("\\arctan", obj["outline"])
        self.assertIn("负倒数", obj["pitfalls"])
        self.assertEqual(obj["reason"], "关键公式需要提示。")

    def test_keeps_valid_json(self):
        raw = '{"outline":"a","suggested":"good"}'
        self.assertEqual(speech.parse_model_json(raw), {"outline": "a", "suggested": "good"})

    def test_returns_none_for_garbage(self):
        self.assertIsNone(speech.parse_model_json("不是 JSON，也没有花括号"))

    def test_summarize_problem_does_not_use_raw_json_as_outline(self):
        original = speech.chat_completion
        try:
            speech.chat_completion = lambda *a, **k: (
                {"choices": [{"message": {"content": BROKEN}}]}, "deepseek", "deepseek-flash"
            )
            rubric = speech.summarize_problem({"text": "题目"}, [{"role": "user", "content": "讲题"}])
        finally:
            speech.chat_completion = original
        self.assertTrue(rubric["outline"].startswith("1. 求导"))
        self.assertNotIn('"outline"', rubric["outline"])
        self.assertEqual(rubric["suggested"], "hard")


if __name__ == "__main__":
    unittest.main()
