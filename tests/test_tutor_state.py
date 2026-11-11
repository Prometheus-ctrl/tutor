import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import app_api  # noqa: E402
import db  # noqa: E402


class TutorStateTest(unittest.TestCase):
    def setUp(self):
        self.old_db = db.DB
        self.tmp = tempfile.TemporaryDirectory()
        db.DB = os.path.join(self.tmp.name, "app.db")
        db.init(db.DB)

    def tearDown(self):
        db.DB = self.old_db
        self.tmp.cleanup()

    def test_state_roundtrip(self):
        sid = "s:test:tutor-state"
        self.assertEqual(app_api.get_tutor_state(sid), {})
        self.assertTrue(app_api.save_tutor_state(sid, {"probes": 1, "hint_level": 0}))
        self.assertEqual(app_api.get_tutor_state(sid)["probes"], 1)
        self.assertTrue(app_api.save_tutor_state(sid, {"probes": 2, "hint_level": 1}))
        self.assertEqual(app_api.get_tutor_state(sid)["hint_level"], 1)


if __name__ == "__main__":
    unittest.main()
