import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import app_api  # noqa: E402
import db  # noqa: E402

TID = "w:test:revision"


class WritingRevisionTest(unittest.TestCase):
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

    def tearDown(self):
        c = db.connect()
        c.execute("DELETE FROM writing_revisions WHERE writing_id=?", (TID,))
        c.execute("DELETE FROM writing_tasks WHERE id=?", (TID,))
        c.commit()
        c.close()

    def test_save_and_final_create_snapshots(self):
        app_api.writing_save(TID, "first version")
        app_api.writing_save(TID, "second version")
        app_api.writing_final(TID, "final version")
        c = db.connect()
        rows = c.execute(
            "SELECT kind,draft FROM writing_revisions WHERE writing_id=? ORDER BY created_at",
            (TID,),
        ).fetchall()
        c.close()
        self.assertEqual([r["kind"] for r in rows], ["save", "save", "final"])
        self.assertEqual(rows[-1]["draft"], "final version")


if __name__ == "__main__":
    unittest.main()
