import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import speech  # noqa: E402


class WritingFeedbackClaimTest(unittest.TestCase):
    def setUp(self):
        self.draft = (
            "The chart shows health literacy from 2012 to 2021. "
            "It rose from 8.80% to 25.40%, and reached 23.15% in 2020."
        )

    def test_drops_false_missing_claim_when_all_numbers_exist(self):
        issues = [{
            "quote": "It rose from 8.80% to 25.40%",
            "problem": "忽略了 2021 年 25.40% 这个终点数据。",
            "action": "补上 2021 年 25.40%。",
        }]
        kept, _ = speech._clean_feedback_claims(issues, "", self.draft)
        self.assertEqual(kept, [])

    def test_keeps_real_missing_data_claim(self):
        issues = [{
            "quote": "It rose from 8.80% to 25.40%",
            "problem": "没有提到 2018 年 17.06% 和 2019 年 19.17% 的连续跃升。",
            "action": "补入 2018、2019 两个具体数据点。",
        }]
        kept, _ = speech._clean_feedback_claims(issues, "", self.draft)
        self.assertEqual(len(kept), 1)

    def test_replaces_false_next_action(self):
        issues = [{
            "quote": "It rose from 8.80% to 25.40%",
            "problem": "缺少趋势节点。",
            "action": "补入 2018 年 17.06% 的节点。",
        }]
        _, nxt = speech._clean_feedback_claims(
            issues, "加入 2021 年 25.40% 的终点数据。", self.draft
        )
        self.assertEqual(nxt, "补入 2018 年 17.06% 的节点。")


class WritingFeedbackStructureTest(unittest.TestCase):
    def setUp(self):
        self.original = speech.chat_completion
        self.draft = (
            "The chart shows health literacy in China from 2012 to 2021. "
            "It rose from 8.80% to 25.40%. In 2012, only a small share of people "
            "understood basic health information, but by 2021 the figure had increased "
            "to about one quarter of the population. Several factors may explain this trend. "
            "First, the government has invested more in public health education. "
            "Second, social media has made health knowledge easier to access. "
            "For example, many communities now offer free health lectures, and schools "
            "and workplaces organize regular health checks. These measures help people "
            "understand how to prevent disease and how to respond to common health problems. "
            "In my view, this progress is encouraging, but more efforts are needed in rural areas."
        )

    def tearDown(self):
        speech.chat_completion = self.original

    def _fake(self, payload):
        def fake(messages, **kwargs):
            return {"choices": [{"message": {"content": __import__("json").dumps(payload)}}]}, "fake", "fake-model"
        speech.chat_completion = fake

    def test_hard_issue_requires_rewrite(self):
        self._fake({
            "must_fix": [{
                "quote": "It rose from 8.80% to 25.40%.",
                "problem": "图表终点与前一句的年份范围没有连起来，读者看不到趋势。",
                "fix": "补一句趋势解释。",
            }],
            "optional": ["可以用 more than doubled 替换 rose。"],
            "rewrite_required": True,
            "scores": {"task": 8, "structure": 8, "language": 8},
        })
        out = speech.review_writing("prompt", self.draft, part="B")
        self.assertTrue(out["rewrite_required"])
        self.assertEqual(len(out["must_fix"]), 1)
        self.assertTrue(out["next_action"].startswith("这次只改："))
        self.assertEqual(len(out["optional"]), 1)

    def test_no_hard_issue_allows_finalize(self):
        self._fake({
            "must_fix": [],
            "optional": ["可以用 more than doubled 替换 rose。"],
            "rewrite_required": True,
            "scores": {"task": 9, "structure": 9, "language": 9},
        })
        out = speech.review_writing("prompt", self.draft, part="B")
        self.assertFalse(out["rewrite_required"])
        self.assertEqual(out["must_fix"], [])
        self.assertEqual(out["next_action"], "")
        self.assertEqual(len(out["optional"]), 1)

    def test_hallucinated_quote_is_dropped(self):
        self._fake({
            "must_fix": [{
                "quote": "This sentence is not in the draft.",
                "problem": "句子读不懂。",
                "fix": "重写这一句。",
            }],
            "rewrite_required": True,
            "scores": {"task": 5, "structure": 5, "language": 5},
        })
        out = speech.review_writing("prompt", self.draft, part="B")
        self.assertEqual(out["must_fix"], [])
        self.assertFalse(out["rewrite_required"])
        self.assertEqual(out["next_action"], "")

    def test_keeps_higher_severity_issue(self):
        self._fake({
            "must_fix": [
                {"quote": "It rose from 8.80% to 25.40%.", "problem": "E. 语法错误。", "fix": "改语法。"},
                {"quote": "It rose from 8.80% to 25.40%.", "problem": "A. 图表数据看错。", "fix": "改数据。"},
            ],
            "rewrite_required": True,
            "scores": {"task": 8, "structure": 8, "language": 8},
        })
        out = speech.review_writing("prompt", self.draft, part="B")
        self.assertEqual(len(out["must_fix"]), 1)
        self.assertTrue(out["must_fix"][0]["problem"].startswith("A."))

    def test_unlabeled_issue_uses_keyword_severity(self):
        self._fake({
            "must_fix": [
                {"quote": "It rose from 8.80% to 25.40%.", "problem": "语法错误：主谓不一致。", "fix": "改语法。"},
                {"quote": "It rose from 8.80% to 25.40%.", "problem": "图表数据看错：终点百分比不对。", "fix": "改数据。"},
            ],
            "rewrite_required": True,
            "scores": {"task": 8, "structure": 8, "language": 8},
        })
        out = speech.review_writing("prompt", self.draft, part="B")
        self.assertEqual(len(out["must_fix"]), 1)
        self.assertIn("图表数据", out["must_fix"][0]["problem"])

    def test_data_keyword_in_grammar_issue_does_not_outrank(self):
        self._fake({
            "must_fix": [
                {"quote": "It rose from 8.80% to 25.40%.", "problem": "数据表明逻辑清楚，但主谓不一致。", "fix": "改语法。"},
                {"quote": "It rose from 8.80% to 25.40%.", "problem": "图表数据看错：终点百分比不对。", "fix": "改数据。"},
            ],
            "rewrite_required": True,
            "scores": {"task": 8, "structure": 8, "language": 8},
        })
        out = speech.review_writing("prompt", self.draft, part="B")
        self.assertEqual(len(out["must_fix"]), 1)
        self.assertIn("图表数据", out["must_fix"][0]["problem"])

    def test_positive_task_phrase_does_not_outrank_missing_task(self):
        self._fake({
            "must_fix": [
                {"quote": "It rose from 8.80% to 25.40%.", "problem": "任务完成得很好，但主谓不一致。", "fix": "改语法。"},
                {"quote": "It rose from 8.80% to 25.40%.", "problem": "题目要求没覆盖：缺少建议。", "fix": "补建议。"},
            ],
            "rewrite_required": True,
            "scores": {"task": 8, "structure": 8, "language": 8},
        })
        out = speech.review_writing("prompt", self.draft, part="B")
        self.assertEqual(len(out["must_fix"]), 1)
        self.assertIn("没覆盖", out["must_fix"][0]["problem"])

    def test_positive_logic_phrase_does_not_outrank_real_gap(self):
        self._fake({
            "must_fix": [
                {"quote": "It rose from 8.80% to 25.40%.", "problem": "逻辑清晰，但主谓不一致。", "fix": "改语法。"},
                {"quote": "It rose from 8.80% to 25.40%.", "problem": "段落之间没有过渡，逻辑断。", "fix": "加过渡。"},
            ],
            "rewrite_required": True,
            "scores": {"task": 8, "structure": 8, "language": 8},
        })
        out = speech.review_writing("prompt", self.draft, part="B")
        self.assertEqual(len(out["must_fix"]), 1)
        self.assertIn("逻辑断", out["must_fix"][0]["problem"])

    def test_positive_grammar_phrase_does_not_outrank_real_error(self):
        self._fake({
            "must_fix": [
                {"quote": "It rose from 8.80% to 25.40%.", "problem": "语法准确，但内容空洞。", "fix": "补内容。"},
                {"quote": "It rose from 8.80% to 25.40%.", "problem": "语法错误：主谓不一致。", "fix": "改语法。"},
            ],
            "rewrite_required": True,
            "scores": {"task": 8, "structure": 8, "language": 8},
        })
        out = speech.review_writing("prompt", self.draft, part="B")
        self.assertEqual(len(out["must_fix"]), 1)
        self.assertIn("语法错误", out["must_fix"][0]["problem"])

    def test_positive_sentence_phrase_does_not_outrank_unreadable(self):
        self._fake({
            "must_fix": [
                {"quote": "It rose from 8.80% to 25.40%.", "problem": "句子通顺，但主谓不一致。", "fix": "改语法。"},
                {"quote": "It rose from 8.80% to 25.40%.", "problem": "句子读不懂：指代混乱。", "fix": "重写句子。"},
            ],
            "rewrite_required": True,
            "scores": {"task": 8, "structure": 8, "language": 8},
        })
        out = speech.review_writing("prompt", self.draft, part="B")
        self.assertEqual(len(out["must_fix"]), 1)
        self.assertIn("读不懂", out["must_fix"][0]["problem"])

    def test_chart_data_is_injected_into_prompt(self):
        captured = {}

        def fake(messages, **kwargs):
            captured["text"] = messages[0]["content"]
            return {"choices": [{"message": {"content": __import__("json").dumps({
                "must_fix": [], "optional": [], "rewrite_required": False,
                "scores": {"task": 9, "structure": 9, "language": 9},
            })}}]}, "fake", "fake-model"

        speech.chat_completion = fake
        out = speech.review_writing(
            "prompt", self.draft, part="B",
            chart_data={"type": "static", "labels": ["pressure relief"], "series": [{"name": "占比", "values": [33]}]},
        )
        self.assertIn("图表数据（以此为准）", captured["text"])
        self.assertIn("pressure relief", captured["text"])
        self.assertFalse(out["rewrite_required"])

    def test_short_draft_gets_one_length_issue(self):
        self._fake({
            "must_fix": [],
            "optional": ["可以用更正式的表达。"],
            "rewrite_required": False,
            "scores": {"task": 8, "structure": 8, "language": 8},
        })
        out = speech.review_writing("prompt", "The chart shows a small increase.", part="B")
        self.assertTrue(out["rewrite_required"])
        self.assertEqual(len(out["must_fix"]), 1)
        self.assertTrue(out["must_fix"][0]["problem"].startswith("字数明显不足"))
        self.assertIn("150 词", out["next_action"])


if __name__ == "__main__":
    unittest.main()
