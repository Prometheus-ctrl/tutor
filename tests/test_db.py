import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import db  # noqa: E402


class AppDbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "app.db")
        db.init(self.path)
        self.c = db.connect(self.path)
        now = db.now()
        self.c.execute("INSERT INTO subjects(id,name,code,created_at) VALUES('math2','数学二','math2',?)", (now,))
        self.c.execute("INSERT INTO goals(id,subject_id,title,created_at) VALUES('g1','math2','数二',?)", (now,))
        self.c.execute("INSERT INTO tasks(id,goal_id,title,created_at) VALUES('t1','g1','真题',?)", (now,))
        self.c.execute("INSERT INTO plans(id,task_id,name,year,created_at) VALUES('p1','t1','2010 真题',2010,?)", (now,))
        self.c.execute("INSERT INTO papers(id,plan_id,subject_id,title,created_at) VALUES('paper1','p1','math2','2010 真题',?)", (now,))
        self.c.execute(
            "INSERT INTO problems(id,paper_id,subject_id,type,no,text,status,created_at) "
            "VALUES('paper1:0','paper1','math2','single','1','题干','new',?)", (now,)
        )
        self.c.commit()

    def tearDown(self):
        self.c.close()
        self.tmp.cleanup()

    def test_hierarchy_and_summary(self):
        s = db.summary(self.path)
        self.assertEqual(s["subjects"], 1)
        self.assertEqual(s["papers"], 1)
        self.assertEqual(s["problems"], 1)
        row = self.c.execute(
            "SELECT s.name, g.title, t.title, p.name, x.title "
            "FROM subjects s JOIN goals g ON g.subject_id=s.id "
            "JOIN tasks t ON t.goal_id=g.id JOIN plans p ON p.task_id=t.id "
            "JOIN papers x ON x.plan_id=p.id"
        ).fetchone()
        self.assertEqual(tuple(row), ("数学二", "数二", "真题", "2010 真题", "2010 真题"))

    def test_review_unique_and_cascade(self):
        now = db.now()
        self.c.execute(
            "INSERT INTO reviews(id,problem_id,fsrs_json,due,created_at,updated_at) "
            "VALUES('r1','paper1:0','{}','2026-10-28T00:00:00+00:00',?,?)", (now, now)
        )
        self.c.commit()
        with self.assertRaises(Exception):
            self.c.execute(
                "INSERT INTO reviews(id,problem_id,fsrs_json,created_at,updated_at) "
                "VALUES('r2','paper1:0','{}',?,?)", (now, now)
            )
        self.c.rollback()
        self.assertEqual(self.c.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
