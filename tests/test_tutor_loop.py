import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import tutor_loop  # noqa: E402
import tutor_policy  # noqa: E402


class FakeGenerate:
    """按队列返回回复，并记录每次收到的 extra。"""

    def __init__(self, replies):
        self.replies = list(replies)
        self.extras = []
        self.calls = 0

    def __call__(self, text, history, context, extra, meta):
        self.calls += 1
        self.extras.append(extra)
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(r, Exception):
            raise r
        return {"text": r, "speech": r}


class TutorLoopTest(unittest.TestCase):
    def test_probe_one_question_passes_first_try(self):
        gen = FakeGenerate(["这一步为什么成立？"])
        loop = tutor_loop.TutorLoop(generate=gen)
        out = loop.step("这题选 B")
        self.assertEqual(out["action"], "probe")
        self.assertTrue(out["trace"]["valid"])
        self.assertEqual(out["trace"]["attempts"], 1)
        self.assertEqual(out["text"], "这一步为什么成立？")
        self.assertIn("【本轮教学动作】", gen.extras[0])
        self.assertIn("追问", gen.extras[0])

    def test_invalid_reply_is_retried_with_contract_feedback(self):
        gen = FakeGenerate(["这一步为什么？那下一步呢？", "这一步为什么成立？"])
        loop = tutor_loop.TutorLoop(generate=gen)
        out = loop.step("这题选 B")
        self.assertTrue(out["trace"]["valid"])
        self.assertEqual(out["trace"]["attempts"], 2)
        self.assertIn("【上一条不合格】", gen.extras[1])
        self.assertIn("恰好包含一个问句", gen.extras[1])

    def test_all_invalid_falls_back(self):
        gen = FakeGenerate(["？？"])
        loop = tutor_loop.TutorLoop(generate=gen, max_retries=2)
        out = loop.step("这题选 B")
        self.assertFalse(out["trace"]["valid"])
        self.assertTrue(out["trace"]["fallback"])
        self.assertEqual(out["trace"]["attempts"], 3)
        self.assertEqual(out["text"], tutor_policy.fallback_text("probe"))
        self.assertNotIn("？", tutor_policy.fallback_text("probe"))

    def test_generate_exception_falls_back_without_retry(self):
        gen = FakeGenerate([RuntimeError("模型超时")])
        loop = tutor_loop.TutorLoop(generate=gen, max_retries=2)
        out = loop.step("这题选 B")
        self.assertTrue(out["trace"]["fallback"])
        self.assertEqual(out["trace"]["attempts"], 1)
        self.assertIn("模型超时", out["trace"]["error"])
        self.assertTrue(out["text"])

    def test_stuck_escalates_hint_ladder_across_steps(self):
        gen = FakeGenerate(["提示：先看左子树的访问顺序。下一步：说说根节点之后去哪。"])
        loop = tutor_loop.TutorLoop(generate=gen)
        state = tutor_policy.initial_state()
        for level in (1, 2):
            out = loop.step("这一步我不会做", state=state)
            state = out["state"]
            self.assertEqual(out["action"], "hint")
            self.assertEqual(state["hint_level"], level)

    def test_hint_ladder_resets_after_advance(self):
        gen = FakeGenerate(["好，继续。", "接下来你看哪一步？"])
        loop = tutor_loop.TutorLoop(generate=gen)
        state = {"hint_level": 3, "probes": 0, "checked": False, "last_action": "hint"}
        out = loop.step("因为左子树先被访问", state=state)
        self.assertEqual(out["action"], "advance")
        self.assertEqual(out["state"]["hint_level"], 0)
        out = loop.step("右子树也类似", state=out["state"])
        self.assertEqual(out["action"], "probe")

    def test_claim_understanding_triggers_check(self):
        gen = FakeGenerate(["用你自己的话复述一下关键这一步。"])
        loop = tutor_loop.TutorLoop(generate=gen)
        out = loop.step("我懂了")
        self.assertEqual(out["action"], "check")
        self.assertTrue(out["state"]["checked"])

    def test_pause_on_frustration(self):
        gen = FakeGenerate(["先停一下，这题现在不适合硬扛。你可以选：休息两分钟、只做一小步、或者换一道。"])
        loop = tutor_loop.TutorLoop(generate=gen)
        out = loop.step("我不想做了，烦死了")
        self.assertEqual(out["action"], "pause")

    def test_every_action_has_prompt_and_contract(self):
        for action in tutor_policy.ACTIONS:
            brief = tutor_loop.build_action_prompt(action)
            self.assertTrue(brief["prompt"])
            self.assertTrue(brief["contract"])
            self.assertIn("【本轮教学动作】", brief["prompt"])

    def test_generate_receives_meta_and_history(self):
        seen = {}

        def gen(text, history, context, extra, meta):
            seen["text"] = text
            seen["history"] = history
            seen["meta"] = meta
            return {"text": "为什么先访问根？", "speech": "为什么先访问根？"}

        loop = tutor_loop.TutorLoop(generate=gen)
        hist = [{"role": "user", "content": "上一步"}]
        loop.step("那左子树呢", history=hist, meta={"model": "deepseek-flash"})
        self.assertEqual(seen["text"], "那左子树呢")
        self.assertEqual(seen["history"], hist)
        self.assertEqual(seen["meta"]["model"], "deepseek-flash")

    def test_state_engine_tagged(self):
        gen = FakeGenerate(["好，继续。"])
        loop = tutor_loop.TutorLoop(generate=gen)
        out = loop.step("因为先序先根")
        self.assertEqual(out["state"]["engine"], "loop")


if __name__ == "__main__":
    unittest.main()
