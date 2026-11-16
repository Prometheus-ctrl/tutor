import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import tutor_policy  # noqa: E402


class TutorPolicyTest(unittest.TestCase):
    def test_student_moves(self):
        cases = {
            "这题选 B": "answer",
            "因为先入先出": "reason",
            "不知道": "stuck",
            "进行不下去了": "stuck",
            "直接讲完整解法": "request_explain",
            "我懂了": "claim_understanding",
            "这题是不是考英语？": "off_topic",
            "我不想做了": "frustration",
        }
        for text, move in cases.items():
            self.assertEqual(tutor_policy.classify_move(text), move, text)

    def test_buhui_is_not_always_stuck(self):
        """“不会出现/会不会”是陈述或提问，不能算学生卡住。"""
        cases = {
            "在这过程中，子树是的层高是不会变化的": "answer",
            "右两边就是跟到父节点那边去，不会出现层高加一": "answer",
            "那是会不会有线索树没有null？ 应该不可能吧": "question",
        }
        for text, move in cases.items():
            self.assertEqual(tutor_policy.classify_move(text), move, text)

    def test_real_stuck_phrases_still_stuck(self):
        cases = (
            "嗯，等一下，二路归并排序我还不会，我得再去看一看视频。",
            "嗯，然后基数排序，我好像一点都不知道，我一无所知。",
            "分桶的那部分不太清楚，就是不知道链表是怎么连的。",
            "这个我不会做",
            "我卡在这里了",
            "我还没懂",
            "不会",
        )
        for text in cases:
            self.assertEqual(tutor_policy.classify_move(text), "stuck", text)

    def test_probe_limit_then_hint(self):
        state = tutor_policy.initial_state()
        action, state = tutor_policy.next_action(state, "answer")
        self.assertEqual(action, "probe")
        action, state = tutor_policy.next_action(state, "answer")
        self.assertEqual(action, "probe")
        action, state = tutor_policy.next_action(state, "answer")
        self.assertEqual(action, "hint")
        self.assertEqual(state["hint_level"], 1)

    def test_stuck_never_probes(self):
        action, state = tutor_policy.next_action({}, "stuck")
        self.assertEqual(action, "hint")
        action, state = tutor_policy.next_action(state, "stuck")
        self.assertEqual(action, "hint")
        self.assertEqual(state["hint_level"], 2)

    def test_frustration_pauses_instead_of_probing(self):
        action, state = tutor_policy.next_action({}, "frustration")
        self.assertEqual(action, "pause")
        self.assertEqual(state["probes"], 0)
        text = tutor_policy.fallback_text("pause")
        self.assertIn("停一下", text)
        self.assertFalse(text.endswith("？"))

    def test_claim_understanding_requires_check(self):
        action, state = tutor_policy.next_action({}, "claim_understanding")
        self.assertEqual(action, "check")
        self.assertTrue(state["checked"])

    def test_student_question_gets_explanation_not_probe(self):
        action, state = tutor_policy.next_action({"probes": 2}, "question")
        self.assertEqual(action, "explain")
        self.assertEqual(state["probes"], 0)

    def test_reply_contract(self):
        self.assertTrue(tutor_policy.validate_reply("probe", "你的依据是什么？"))
        self.assertFalse(tutor_policy.validate_reply("probe", "为什么？还有呢？"))
        self.assertFalse(tutor_policy.validate_reply("hint", "再想想？"))
        self.assertTrue(tutor_policy.validate_reply("hint", "提示：先看题目里的依次。"))
        self.assertTrue(tutor_policy.validate_reply("check", "用你自己的话说一遍。"))
        self.assertFalse(tutor_policy.validate_reply("close", "结束。", {}))
        self.assertTrue(tutor_policy.validate_reply("close", "结束。", {"checked": True}))

    def test_fallback_is_not_another_question(self):
        plan = {"stuck": [{"hint": "先写进去的先取出来", "next": "列出前三个数据"}]}
        text = tutor_policy.fallback_text("hint", plan)
        self.assertIn("提示", text)
        self.assertIn("下一步", text)
        self.assertFalse(text.endswith("？"))

    def test_style_flags(self):
        self.assertEqual(tutor_policy.style_flags("太棒了，你太聪明了"), ["praise"])
        self.assertEqual(tutor_policy.style_flags("再想想，具体一点"), ["vague"])
        self.assertEqual(tutor_policy.style_flags("为什么？还有呢？"), ["vague", "multi_question"])
        self.assertEqual(tutor_policy.style_flags("这一步对了，因为先入先出。"), [])

    def test_sanitize_questions_keeps_first(self):
        self.assertEqual(
            tutor_policy.sanitize_questions("这一步对了。那 B 为什么错？C 呢？"),
            "这一步对了。那 B 为什么错？",
        )
        self.assertEqual(tutor_policy.sanitize_questions("没有问号。"), "没有问号。")


if __name__ == "__main__":
    unittest.main()
