import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import app_api  # noqa: E402
import db  # noqa: E402
import speech  # noqa: E402


class LessonPlanTest(unittest.TestCase):
    def setUp(self):
        self.old_db = db.DB
        self.tmp = tempfile.TemporaryDirectory()
        db.DB = os.path.join(self.tmp.name, "app.db")
        db.init(db.DB)
        c = db.connect()
        now = db.now()
        c.execute("INSERT INTO subjects(id,name,code,created_at) VALUES('cs408','408','cs408',?)", (now,))
        c.execute("INSERT INTO papers(id,subject_id,title,created_at) VALUES('p','cs408','测试卷',?)", (now,))
        c.execute(
            "INSERT INTO problems(id,paper_id,subject_id,type,no,text,status,created_at) "
            "VALUES('p:0','p','cs408','single','1','test','new',?)",
            (now,),
        )
        c.commit()
        c.close()

    def tearDown(self):
        db.DB = self.old_db
        self.tmp.cleanup()

    def test_make_lesson_plan_has_progression_fields(self):
        payload = {
            "goal": "理解 FIFO",
            "prerequisites": ["栈 LIFO"],
            "core": ["队列"],
            "path": ["看操作顺序"],
            "misconceptions": [{"wrong": "栈也可以", "why": "混淆进出", "contrast": "队列先进先出"}],
            "stuck": [{"point": "选栈", "hint": "谁先写谁先出", "next": "列出三个数据"}],
            "hint_ladder": [{"level": 1, "cue": "看依次"}, {"level": 2, "cue": "先写先取"}],
            "check_questions": ["为什么不是栈？"],
            "success_criteria": ["能排除栈"],
            "max_followups": 5,
            "finish_check": ["说出 FIFO"],
        }
        fake = (
            {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]},
            "test",
            "test",
        )
        with mock.patch.object(speech, "chat_completion", return_value=fake):
            plan = speech.make_lesson_plan({"text": "打印机缓冲区"})
        self.assertEqual(plan["goal"], "理解 FIFO")
        self.assertEqual(plan["max_followups"], 2)
        self.assertEqual(plan["stuck"][0]["hint"], "谁先写谁先出")
        self.assertEqual(plan["prerequisites"], ["栈 LIFO"])
        self.assertEqual(plan["misconceptions"][0]["wrong"], "栈也可以")
        self.assertEqual(plan["hint_ladder"][1]["cue"], "先写先取")
        self.assertEqual(plan["check_questions"], ["为什么不是栈？"])
        self.assertEqual(plan["success_criteria"], ["能排除栈"])

    def test_lesson_plan_cache_roundtrip(self):
        app_api.save_lesson_plan("p:0", {"goal": "x", "core": []})
        self.assertEqual(app_api.get_lesson_plan("p:0")["goal"], "x")

    def test_merge_finish_check(self):
        rubric = {"outline": "x"}
        plan = {"finish_check": ["说出 FIFO"], "check_questions": ["为什么不是栈？"]}
        merged = speech.merge_finish_check(rubric, plan)
        self.assertEqual(merged["finish_check"], ["说出 FIFO"])
        self.assertEqual(merged["check_questions"], ["为什么不是栈？"])
        self.assertEqual(merged["outline"], "x")


if __name__ == "__main__":
    unittest.main()
