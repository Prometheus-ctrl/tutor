import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import tutor_router  # noqa: E402


class TutorRouterTest(unittest.TestCase):
    def test_role_signals(self):
        cases = {
            "我讲完了，帮我看看有没有漏": "gap_check",
            "这里我不懂，帮我补一下": "gap_fill",
            "别直接告诉我，问我": "guide",
            "差不多了，帮我总结一下": "summary",
        }
        for text, role in cases.items():
            self.assertEqual(tutor_router.route(text)["role"], role, text)

    def test_answering_question_is_listening(self):
        history = [
            {"role": "assistant", "content": "2 的右子树是哪些结点？"},
        ]
        self.assertEqual(tutor_router.route("7、5、6", history)["role"], "listening")

    def test_normal_explanation_stays_listening(self):
        self.assertEqual(tutor_router.route("我先看根结点，然后分左右段")["role"], "listening")


if __name__ == "__main__":
    unittest.main()
