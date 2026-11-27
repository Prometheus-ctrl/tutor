import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import tutor_replay  # noqa: E402


class PairTurnsTest(unittest.TestCase):
    def test_pairs_user_with_following_assistant(self):
        turns = [
            {"role": "user", "content": "a1"},
            {"role": "assistant", "content": "r1"},
            {"role": "user", "content": "a2"},
            {"role": "assistant", "content": "r2"},
        ]
        self.assertEqual(
            tutor_replay.pair_turns(turns),
            [("a1", "r1"), ("a2", "r2")],
        )

    def test_user_without_assistant_keeps_pending(self):
        turns = [{"role": "user", "content": "a1"}, {"role": "user", "content": "a2"}]
        self.assertEqual(tutor_replay.pair_turns(turns), [("a1", None), ("a2", None)])

    def test_summary_role_is_skipped(self):
        turns = [
            {"role": "user", "content": "a1"},
            {"role": "assistant", "content": "r1"},
            {"role": "summary", "content": "s1"},
            {"role": "user", "content": "a2"},
        ]
        self.assertEqual(tutor_replay.pair_turns(turns), [("a1", "r1"), ("a2", None)])


class ReplaySessionTest(unittest.TestCase):
    def test_replay_produces_trace_per_round(self):
        turns = [
            {"role": "user", "content": "这题选 B"},
            {"role": "assistant", "content": "为什么选 B？"},
            {"role": "user", "content": "不会"},
            {"role": "assistant", "content": "先看选项的提示"},
        ]
        traces = tutor_replay.replay_session(turns)
        self.assertEqual(len(traces), 2)
        self.assertEqual(traces[0]["action"], "probe")
        self.assertTrue(traces[0]["valid"])
        self.assertEqual(traces[1]["action"], "hint")
        self.assertTrue(traces[1]["valid"])


if __name__ == "__main__":
    unittest.main()
