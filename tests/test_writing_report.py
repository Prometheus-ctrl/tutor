import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import app_api  # noqa: E402
import db  # noqa: E402
import writing_report  # noqa: E402

TID = "w:test:report"


class WritingReportTest(unittest.TestCase):
    def setUp(self):
        db.init()
        c = db.connect()
        c.execute("DELETE FROM writing_revisions WHERE writing_id=?", (TID,))
        c.execute("DELETE FROM writing_tasks WHERE id=?", (TID,))
        c.execute(
            "INSERT INTO writing_tasks(id,prompt,status,created_at,updated_at) VALUES(?,?,?,?,?)",
            (TID, "Test prompt.", "draft", db.now(), db.now()),
        )
        c.commit()
        c.close()
        app_api.writing_save(TID, "first draft short.")
        app_api.writing_save(TID, "first draft short. Second sentence added.")
        app_api.writing_final(TID, "first draft short. Second sentence added. Final sentence.")

    def tearDown(self):
        c = db.connect()
        c.execute("DELETE FROM writing_revisions WHERE writing_id=?", (TID,))
        c.execute("DELETE FROM writing_tasks WHERE id=?", (TID,))
        c.commit()
        c.close()

    def test_timeline_keeps_insertion_order(self):
        task = writing_report.load_task(TID)
        revisions = writing_report.load_revisions(TID)
        report = writing_report.build_report(task, revisions)
        self.assertIn("修改时间线", report)
        self.assertLess(report.index("保存：3 词"), report.index("保存：6 词"))
        self.assertLess(report.index("保存：6 词"), report.index("定稿：8 词"))

    def test_report_does_not_judge_mastery(self):
        task = writing_report.load_task(TID)
        report = writing_report.build_report(task, writing_report.load_revisions(TID))
        body = report.split("> 报告")[0]
        self.assertNotIn("已掌握", body)
        self.assertNotIn("能力提升", body)
        self.assertIn("下一次只练什么", report)

    def test_missing_content_is_not_reported_as_resolved_by_quote_absence(self):
        import json

        first = "I am writing to thank you for your congratulations. I will write to you again soon."
        current = first + " In my opinion, you should read widely and keep a notebook."
        feedback = {
            "must_fix": [{
                "problem": "题目要求没覆盖：缺少 advice。",
                "quote": "I will write to you again soon.",
                "action": "补一条具体建议。",
            }],
            "optional": ["可以用更正式的表达。"],
        }
        task = {
            "id": "w:test:S1:A",
            "first_draft": first,
            "draft": current,
            "feedback": json.dumps(feedback, ensure_ascii=False),
        }
        revisions = [
            {"kind": "save", "draft": first, "feedback": None, "created_at": 1001},
            {"kind": "feedback", "draft": first, "feedback": json.dumps(feedback, ensure_ascii=False), "created_at": 1002},
            {"kind": "save", "draft": current, "feedback": None, "created_at": 1003},
        ]
        report = writing_report.build_report(task, revisions)
        self.assertIn("缺失类问题", report)
        self.assertNotIn("原问题句已不在当前稿", report)

    def test_repeated_feedback_is_grouped(self):
        import json

        text = "Short draft."
        feedback = {"must_fix": [{"problem": "字数不足", "quote": text, "action": "补内容"}]}
        task = {"id": "w:test:dup:B", "first_draft": text, "draft": text,
                "feedback": json.dumps(feedback, ensure_ascii=False)}
        revisions = [
            {"kind": "feedback", "draft": text, "feedback": json.dumps(feedback, ensure_ascii=False), "created_at": 1001},
            {"kind": "feedback", "draft": text, "feedback": json.dumps(feedback, ensure_ascii=False), "created_at": 1002},
        ]
        report = writing_report.build_report(task, revisions)
        self.assertIn("重复 2 次", report)
        self.assertEqual(report.count("硬伤：字数不足"), 1)


if __name__ == "__main__":
    unittest.main()
