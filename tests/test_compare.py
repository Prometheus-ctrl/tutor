import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import speech  # noqa: E402


class CompareWithPlanTest(unittest.TestCase):
    def test_compare_returns_only_comparison_arrays(self):
        payload = {
            "hit": ["说出了 FIFO"],
            "miss": ["没有排除栈"],
            "confused": ["把栈当成先进先出"],
            "extra": ["提到了缓存"],
        }
        fake = (
            {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]},
            "test",
            "test",
        )
        plan = {"goal": "理解 FIFO", "core": ["队列"], "finish_check": ["能排除栈"]}
        with mock.patch.object(speech, "chat_completion", return_value=fake):
            result = speech.compare_with_plan(plan, "队列是先进先出")
        self.assertEqual(result["hit"], ["说出了 FIFO"])
        self.assertEqual(result["miss"], ["没有排除栈"])
        self.assertEqual(result["confused"], ["把栈当成先进先出"])
        self.assertEqual(result["extra"], ["提到了缓存"])
        self.assertNotIn("advice", result)

    def test_compare_rejects_empty(self):
        with self.assertRaises(RuntimeError):
            speech.compare_with_plan({"goal": "x"}, "")
        with self.assertRaises(RuntimeError):
            speech.compare_with_plan({}, "answer")


if __name__ == "__main__":
    unittest.main()
