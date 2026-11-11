import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import db  # noqa: E402
import app_api  # noqa: E402


class WritingFlowTest(unittest.TestCase):
    def setUp(self):
        self.old_db = db.DB
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "app.db")
        db.DB = self.path
        db.init(self.path)
        c = db.connect()
        now = db.now()
        c.execute("INSERT INTO subjects(id,name,code,created_at) VALUES('english2','英语二','english2',?)", (now,))
        c.execute("INSERT INTO goals(id,subject_id,title,created_at) VALUES('g','english2','英二',?)", (now,))
        c.execute("INSERT INTO tasks(id,goal_id,title,created_at) VALUES('t','g','真题',?)", (now,))
        c.execute("INSERT INTO plans(id,task_id,name,year,created_at) VALUES('p','t','英语二 历年真题',2023,?)", (now,))
        c.execute("INSERT INTO writing_tasks(id,plan_id,prompt,status,created_at,updated_at) VALUES('w','p','prompt','feedback',?,?)", (now, now))
        c.execute("INSERT INTO daily_plans(id,date,available_min,status,created_at,updated_at) VALUES('day','2026-10-27',90,'draft',?,?)", (now, now))
        c.execute("INSERT INTO queue_items(id,daily_plan_id,subject_id,type,ref_id,estimate_min,sort,status,actual_min,title,created_at) "
                  "VALUES('q','day','english2','writing','w',25,1,'opened',0,'写作',?)", (now,))
        c.commit()
        c.close()

    def tearDown(self):
        db.DB = self.old_db
        self.tmp.cleanup()

    def test_final_marks_queue_done_and_counts_minutes_once(self):
        app_api.writing_final("w", "final text")
        app_api.writing_final("w", "final text")
        c = db.connect()
        row = c.execute("SELECT status,actual_min FROM queue_items WHERE id='q'").fetchone()
        self.assertEqual(row["status"], "done")
        self.assertEqual(row["actual_min"], 25)
        budget = c.execute(
            "SELECT actual_min FROM weekly_budgets WHERE week=? AND subject_id='english2'",
            (app_api._week_start(),),
        ).fetchone()
        self.assertEqual(budget["actual_min"], 25)
        c.close()


if __name__ == "__main__":
    unittest.main()
