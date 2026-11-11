import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import learning_report  # noqa: E402


class LearningReportTest(unittest.TestCase):
    def test_raw_report_has_facts_and_no_mastery_verdict(self):
        facts = {
            "date": "2026-10-28",
            "sessions": 2,
            "turns": 20,
            "minutes": 55,
            "finished": 3,
            "subjects": [{"subject": "cs408", "sessions": 1, "turns": 12}],
            "ratings": [{"rating": "good", "n": 2}],
            "writing": [{"id": "w:test", "status": "final", "final_at": 1}],
        }
        raw = learning_report.build_raw(facts)
        self.assertIn("2026-10-28", raw)
        self.assertIn("55", raw)
        self.assertIn("408", raw)
        self.assertNotIn("已掌握", raw)
        self.assertNotIn("能力提升", raw)

    def test_save_and_load_roundtrip(self):
        old = learning_report.REPORTS
        with tempfile.TemporaryDirectory() as d:
            learning_report.REPORTS = d
            try:
                facts = {"date": "2026-10-28", "sessions": 0, "turns": 0, "minutes": 0,
                         "finished": 0, "subjects": [], "ratings": [], "writing": []}
                raw = learning_report.build_raw(facts)
                learning_report.save("2026-10-28", facts, raw, "# 简报\n\n内容")
                data = learning_report.load("2026-10-28")
                self.assertIn("简报", data["report"])
                self.assertIn("学习记录", data["raw"])
                self.assertEqual(learning_report.list_reports(), ["2026-10-28"])
            finally:
                learning_report.REPORTS = old


if __name__ == "__main__":
    unittest.main()
