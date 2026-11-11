import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import app_api  # noqa: E402
import db  # noqa: E402


class ProblemStateTest(unittest.TestCase):
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

    def test_open_session_marks_in_session(self):
        self.assertTrue(app_api.mark_problem_in_session("p", 0))
        c = db.connect()
        status = c.execute("SELECT status FROM problems WHERE id='p:0'").fetchone()[0]
        c.close()
        self.assertEqual(status, "in_session")

    def test_review_sync_marks_scheduled(self):
        fsrs = {"due": "2026-10-29T00:00:00+00:00", "state_name": "review"}
        self.assertTrue(app_api.sync_review("p:0", fsrs, {"user": "summary"}))
        c = db.connect()
        status = c.execute("SELECT status FROM problems WHERE id='p:0'").fetchone()[0]
        review = c.execute("SELECT COUNT(*) FROM reviews WHERE problem_id='p:0'").fetchone()[0]
        c.close()
        self.assertEqual(status, "scheduled")
        self.assertEqual(review, 1)

    def test_paper_detail_exposes_last_session(self):
        c = db.connect()
        c.execute(
            "INSERT INTO sessions(id,problem_id,paper_id,mode,started_at) VALUES('s','p:0','p','tutor',1000)"
        )
        c.execute(
            "INSERT INTO turns(session_id,role,content,created_at) VALUES('s','user','hello',1001)"
        )
        c.execute(
            "INSERT INTO sessions(id,problem_id,paper_id,mode,started_at) VALUES('empty','p:0','p','tutor',2000)"
        )
        c.commit()
        c.close()
        data = app_api.paper_detail("p")
        p = data["problems"][0]
        self.assertEqual(p["last_session_at"], 1000)
        self.assertEqual(p["last_session_turns"], 1)
        self.assertTrue(p["last_session_open"])


if __name__ == "__main__":
    unittest.main()
