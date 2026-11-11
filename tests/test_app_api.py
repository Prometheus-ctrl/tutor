import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import db  # noqa: E402
import app_api  # noqa: E402


class TimeApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "app.db")
        db.DB = self.path
        db.init(self.path)
        c = db.connect()
        now = db.now()
        for sid, name in [("math2", "数学二"), ("english2", "英语二"), ("politics", "政治"), ("cs408", "408")]:
            c.execute("INSERT INTO subjects(id,name,code,created_at) VALUES(?,?,?,?)", (sid, name, sid, now))
        week = app_api._week_start()
        for sid, minutes in [("math2", 900), ("cs408", 1140), ("english2", 480), ("politics", 480)]:
            c.execute("INSERT INTO weekly_budgets(week,subject_id,planned_min,actual_min,locked) VALUES(?,?,?,0,1)",
                      (week, sid, minutes))
        c.execute("INSERT INTO goals(id,subject_id,title,created_at) VALUES('g1','math2','数二',?)", (now,))
        c.execute("INSERT INTO tasks(id,goal_id,title,created_at) VALUES('t1','g1','真题',?)", (now,))
        c.execute("INSERT INTO plans(id,task_id,name,year,created_at) VALUES('p1','t1','2010 真题',2010,?)", (now,))
        c.execute("INSERT INTO papers(id,plan_id,subject_id,title,created_at) VALUES('paper1','p1','math2','2010 真题',?)", (now,))
        c.execute("INSERT INTO problems(id,paper_id,subject_id,type,no,text,status,created_at) "
                  "VALUES('paper1:0','paper1','math2','single','1','题干','new',?)", (now,))
        c.execute("INSERT INTO reviews(id,problem_id,fsrs_json,due,state,created_at,updated_at) "
                  "VALUES('paper1:0','paper1:0','{}','2000-01-01T00:00:00+00:00','review',?,?)", (now, now))
        c.commit()
        c.close()

    def tearDown(self):
        db.DB = os.path.join(HERE, "data", "app.db")
        self.tmp.cleanup()

    def test_due_and_allocation(self):
        over = app_api.overview()
        self.assertEqual(len(over["due"]), 1)
        self.assertEqual(over["subjects"][0]["due"], 1)
        data = app_api.generate_time(None, 60)
        self.assertTrue(data["ok"])
        total = sum(b["minutes"] for b in data["blocks"])
        self.assertLessEqual(total, int(60 * 0.8) + 15)
        types = [it["type"] for b in data["blocks"] for it in b["items"]]
        self.assertIn("review", types)


if __name__ == "__main__":
    unittest.main()
