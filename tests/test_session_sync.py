import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import app_api  # noqa: E402
import db  # noqa: E402

SID = "s:test:doublewrite"


class SessionDoubleWriteTest(unittest.TestCase):
    def tearDown(self):
        c = db.connect()
        c.execute("DELETE FROM turns WHERE session_id=?", (SID,))
        c.execute("DELETE FROM sessions WHERE id=?", (SID,))
        c.commit()
        c.close()

    def test_session_and_turns_mirror_to_app_db(self):
        data = {
            "id": SID,
            "paper": "",
            "index": 0,
            "mode": "tutor",
            "model": "test",
            "created_at": 1000,
            "ended_at": None,
            "turns": [],
        }
        self.assertTrue(app_api.save_session(data))
        self.assertTrue(app_api.append_turn(SID, "user", "hello"))
        self.assertTrue(app_api.append_turn(SID, "assistant", "hi", "hi speech"))
        c = db.connect()
        s = c.execute("SELECT * FROM sessions WHERE id=?", (SID,)).fetchone()
        n = c.execute("SELECT COUNT(*) FROM turns WHERE session_id=?", (SID,)).fetchone()[0]
        c.close()
        self.assertIsNotNone(s)
        self.assertEqual(n, 2)

    def test_sync_history_backfills_existing_session(self):
        data = {
            "id": SID,
            "paper": "",
            "index": 0,
            "mode": "tutor",
            "model": "test",
            "created_at": 1000,
            "ended_at": None,
            "turns": [
                {"role": "user", "content": "hello", "speech": "", "created_at": 1001},
                {"role": "assistant", "content": "hi", "speech": "hi", "created_at": 1002},
            ],
        }
        self.assertTrue(app_api.sync_session_history(data))
        c = db.connect()
        n = c.execute("SELECT COUNT(*) FROM turns WHERE session_id=?", (SID,)).fetchone()[0]
        c.close()
        self.assertEqual(n, 2)


if __name__ == "__main__":
    unittest.main()
