import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import writing_expansion  # noqa: E402


class WritingExpansionTest(unittest.TestCase):
    def test_part_b_reports_data_example_comment_slots(self):
        draft = (
            "The chart shows health literacy in China from 2012 to 2021. "
            "In 2012 it was 8.80%, but by 2021 it rose to 25.40%. "
            "Several factors account for this trend, especially economic growth."
        )
        slots = writing_expansion.expansion_advice("B", draft, 150)
        text = " ".join(s["what"] for s in slots)
        self.assertIn("数据点", text)
        self.assertIn("例子", text)
        self.assertIn("评论", text)
        self.assertGreaterEqual(sum(s["words"] for s in slots), 50)

    def test_part_a_gets_three_concrete_slots(self):
        slots = writing_expansion.expansion_advice("A", "Dear Jack, I am writing to invite you.", 100)
        self.assertEqual(len(slots), 3)
        self.assertGreaterEqual(sum(s["words"] for s in slots), 40)
        self.assertTrue(all(s.get("where") and s.get("what") and s.get("starter") for s in slots))

    def test_only_description_gets_cause_example_comment(self):
        draft = (
            "The chart shows health literacy from 2012 to 2021. "
            "It was 8.80% in 2012 and 25.40% in 2021."
        )
        slots = writing_expansion.expansion_advice("B", draft, 150)
        text = " ".join(s["what"] for s in slots)
        self.assertIn("原因", text)
        self.assertIn("例子", text)
        self.assertIn("评论", text)
        self.assertFalse(any("完整范文" in s["what"] for s in slots))

    def test_cause_without_example_gets_example_first(self):
        draft = (
            "The chart shows health literacy from 2012 to 2021. "
            "It was 8.80% in 2012 and 25.40% in 2021. "
            "One reason is that health education became more common."
        )
        slots = writing_expansion.expansion_advice("B", draft, 150)
        self.assertIn("例子", slots[0]["what"])

    def test_complete_content_does_not_duplicate_slots(self):
        draft = (
            "The chart shows health literacy from 2012 to 2021. "
            "It was 8.80% in 2012 and 25.40% in 2021. "
            "One reason is that health education became more common. "
            "For example, community lectures are now widely available. "
            "In my view, this trend is positive."
        )
        slots = writing_expansion.expansion_advice("B", draft, 150)
        self.assertEqual(len({s["what"] for s in slots}), len(slots))


if __name__ == "__main__":
    unittest.main()
