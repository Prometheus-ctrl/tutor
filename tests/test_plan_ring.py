import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import app_api  # noqa: E402
import db  # noqa: E402


class PlanRingTest(unittest.TestCase):
    def setUp(self):
        self.old_db = db.DB
        self.tmp = tempfile.TemporaryDirectory()
        db.DB = os.path.join(self.tmp.name, "app.db")
        db.init(db.DB)
        c = db.connect()
        now = db.now()
        c.execute("INSERT INTO subjects(id,name,code,created_at) VALUES('math2','数二','math2',?)", (now,))
        c.execute("INSERT INTO goals(id,subject_id,title,created_at) VALUES('g','math2','数二目标',?)", (now,))
        c.execute("INSERT INTO tasks(id,goal_id,title,created_at) VALUES('t','g','数二任务',?)", (now,))
        c.execute("INSERT INTO plans(id,task_id,name,year,created_at) VALUES('p','t','数二历年真题',NULL,?)", (now,))
        for year in (2010, 2011):
            pid = "paper-%s" % year
            c.execute(
                "INSERT INTO papers(id,plan_id,subject_id,title,created_at) VALUES(?,?,?,?,?)",
                (pid, "p", "math2", "%s 数二真题" % year, now),
            )
            for i in range(2):
                qid = "%s:%s" % (pid, i)
                c.execute(
                    "INSERT INTO problems(id,paper_id,subject_id,type,no,text,status,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (qid, pid, "math2", "single", str(i + 1), "q", "new", now),
                )
                c.execute(
                    "INSERT INTO plan_units(id,plan_id,paper_id,problem_id,status,created_at) "
                    "VALUES(?,?,?,?,?,?)",
                    ("u-" + qid, "p", pid, qid, "pending", now),
                )
        c.execute("UPDATE tasks SET active_plan_id='p' WHERE id='t'")
        c.commit()
        c.close()

    def tearDown(self):
        db.DB = self.old_db
        self.tmp.cleanup()

    def test_next_problem_is_chronological_then_due_first(self):
        nxt = app_api.next_problem("p")
        self.assertEqual(nxt["paper"], "paper-2010")
        self.assertEqual(nxt["index"], 0)
        c = db.connect()
        c.execute(
            "INSERT INTO reviews(id,problem_id,fsrs_json,due,state,created_at,updated_at) "
            "VALUES('r','paper-2011:0','{}','2020-01-01T00:00:00+00:00','review',?,?)",
            (db.now(), db.now()),
        )
        c.commit()
        c.close()
        nxt = app_api.next_problem("p")
        self.assertEqual(nxt["paper"], "paper-2011")
        self.assertEqual(nxt["index"], 0)

    def test_phase_moves_from_not_started_to_first_done(self):
        c = db.connect()
        plan = c.execute("SELECT * FROM plans WHERE id='p'").fetchone()
        self.assertEqual(app_api._plan_phase(c, plan), "not_started")
        c.execute("UPDATE plan_units SET status='finished' WHERE problem_id='paper-2010:0'")
        c.commit()
        self.assertEqual(app_api._plan_phase(c, plan), "in_progress")
        c.execute("UPDATE plan_units SET status='finished'")
        c.commit()
        self.assertEqual(app_api._plan_phase(c, plan), "first_done")
        c.close()

    def test_next_from_problem_skips_current(self):
        nxt = app_api.next_from_problem("paper-2010", 0)
        self.assertEqual(nxt["paper"], "paper-2010")
        self.assertEqual(nxt["index"], 1)
        nxt = app_api.next_from_problem("paper-2011", 1)
        self.assertEqual(nxt["paper"], "paper-2010")
        self.assertEqual(nxt["index"], 0)

    def test_next_after_crosses_paper_in_plan_order(self):
        nxt = app_api.next_after("paper-2010", 0)
        self.assertEqual(nxt["paper"], "paper-2010")
        self.assertEqual(nxt["index"], 1)
        nxt = app_api.next_after("paper-2010", 1)
        self.assertEqual(nxt["paper"], "paper-2011")
        self.assertEqual(nxt["index"], 0)
        self.assertIsNone(app_api.next_after("paper-2011", 1))

    def test_previous_before_crosses_paper_in_plan_order(self):
        prev = app_api.previous_before("paper-2011", 0)
        self.assertEqual(prev["paper"], "paper-2010")
        self.assertEqual(prev["index"], 1)
        prev = app_api.previous_before("paper-2010", 1)
        self.assertEqual(prev["paper"], "paper-2010")
        self.assertEqual(prev["index"], 0)
        self.assertIsNone(app_api.previous_before("paper-2010", 0))


if __name__ == "__main__":
    unittest.main()
