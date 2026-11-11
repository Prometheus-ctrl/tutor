import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import app_api  # noqa: E402
import db  # noqa: E402


class VocabTest(unittest.TestCase):
    def setUp(self):
        self.old_db = db.DB
        self.tmp = tempfile.TemporaryDirectory()
        db.DB = os.path.join(self.tmp.name, "app.db")
        db.init(db.DB)

    def tearDown(self):
        db.DB = self.old_db
        self.tmp.cleanup()

    def test_add_list_status_delete(self):
        data = app_api.vocab_add("ephemeral", "Fame can be ephemeral.", "")
        self.assertTrue(data["ok"])
        items = app_api.vocab_list()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["word"], "ephemeral")
        self.assertEqual(items[0]["status"], "new")
        app_api.vocab_set_status(data["id"], "known")
        self.assertEqual(app_api.vocab_list()["items"][0]["status"], "known")
        app_api.vocab_delete(data["id"])
        self.assertEqual(app_api.vocab_list()["items"], [])

    def test_word_required(self):
        data = app_api.vocab_add("", "sentence", "")
        self.assertFalse(data["ok"])


if __name__ == "__main__":
    unittest.main()
