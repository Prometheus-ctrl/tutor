import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "server"))
import speech  # noqa: E402


class AsrContextTest(unittest.TestCase):
    def test_context_is_sent_as_system_message(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFFxxxxWAVE")
            path = f.name
        try:
            fake = {"output": {"choices": [{"message": {"content": [{"text": "测试"}]}}]}, "usage": {}}
            with mock.patch.object(speech, "_post", return_value=fake) as post:
                r = speech.transcribe_wav(path, "栈 队列 缓冲区")
            body = post.call_args[0][1]
            self.assertEqual(r["text"], "测试")
            self.assertEqual(body["input"]["messages"][0]["role"], "system")
            self.assertIn("栈 队列 缓冲区", body["input"]["messages"][0]["content"])
            self.assertTrue(body["parameters"]["asr_options"]["enable_itn"])
        finally:
            os.unlink(path)

    def test_no_context_keeps_only_audio_message(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFFxxxxWAVE")
            path = f.name
        try:
            fake = {"output": {"choices": [{"message": {"content": [{"text": "测试"}]}}]}, "usage": {}}
            with mock.patch.object(speech, "_post", return_value=fake) as post:
                speech.transcribe_wav(path, "")
            body = post.call_args[0][1]
            self.assertEqual(len(body["input"]["messages"]), 1)
            self.assertEqual(body["input"]["messages"][0]["role"], "user")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
