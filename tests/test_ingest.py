# -*- coding: utf-8 -*-
"""切题合并的纯函数测试：python -m unittest discover tutor/tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))

import ingest  # noqa: E402
from vision import normalize_bbox  # noqa: E402


class BBoxTest(unittest.TestCase):
    def test_relative(self):
        self.assertEqual(normalize_bbox([0.1, 0.2, 0.5, 0.6], 1000, 2000), [0.1, 0.2, 0.5, 0.6])

    def test_pixel(self):
        self.assertEqual(normalize_bbox([100, 200, 500, 600], 1000, 2000), [0.1, 0.1, 0.5, 0.3])

    def test_clamp(self):
        self.assertEqual(normalize_bbox([-10, 0.2, 1.2, 1.3], 1000, 2000), [0.0, 0.2, 1.0, 1.0])

    def test_bad(self):
        self.assertIsNone(normalize_bbox([0.2, 0.2], 1000, 2000))
        self.assertIsNone(normalize_bbox("x", 1000, 2000))


class MergeTest(unittest.TestCase):
    def test_merge_cd(self):
        prev = {"no": "8", "options": [{"label": "A", "text": "a"}, {"label": "B", "text": "b"}], "continues_next": True}
        lead = {"page": 2, "bbox": [0.1, 0.05, 0.5, 0.1], "options": [{"label": "C", "text": "c"}, {"label": "D", "text": "d"}]}
        info = ingest.merge_leading(prev, lead)
        self.assertTrue(info["merged"])
        self.assertEqual([o["label"] for o in prev["options"]], ["A", "B", "C", "D"])
        self.assertFalse(prev["continues_next"])
        self.assertTrue(prev["merged_from_next"])

    def test_merge_dedupe(self):
        prev = {"no": "1", "options": [{"label": "A", "text": "a"}], "continues_next": True}
        lead = {"page": 2, "options": [{"label": "A", "text": "a"}, {"label": "B", "text": "b"}]}
        ingest.merge_leading(prev, lead)
        self.assertEqual([o["label"] for o in prev["options"]], ["A", "B"])

    def test_merge_text_only(self):
        prev = {"no": "2", "text": "前半", "options": [], "continues_next": True}
        lead = {"page": 2, "text": "后半", "options": []}
        ingest.merge_leading(prev, lead)
        self.assertEqual(prev["continuation_text"], "后半")
        self.assertFalse(prev["continues_next"])


class FinalizeTest(unittest.TestCase):
    def test_crop_boundary(self):
        problems = [
            {"no": "11", "page": 2, "bbox": [0.1, 0.27, 0.9, 0.31]},
            {"no": "12", "page": 2, "bbox": [0.1, 0.31, 0.5, 0.35]},
        ]
        self.assertEqual(ingest.crop_boundary(problems, 0), 0.304)
        self.assertIsNone(ingest.crop_boundary(problems, 1))

    def test_crop_boundary_page_change(self):
        problems = [
            {"no": "8", "page": 1, "bbox": [0.1, 0.86, 0.8, 0.94]},
            {"no": "9", "page": 2, "bbox": [0.1, 0.09, 0.8, 0.16]},
        ]
        self.assertIsNone(ingest.crop_boundary(problems, 0))

    def test_last_page_false_positive(self):
        problems = [{"no": "17", "page": 2, "continues_next": True}]
        warnings = ingest.finalize(problems, 2)
        self.assertFalse(problems[0]["continues_next"])
        self.assertTrue(problems[0]["auto_cleared"])
        self.assertEqual(len(warnings), 1)

    def test_middle_missing(self):
        problems = [{"no": "8", "page": 1, "continues_next": True}, {"no": "9", "page": 2, "continues_next": False}]
        warnings = ingest.finalize(problems, 2)
        self.assertFalse(problems[0]["continues_next"])
        self.assertEqual(len(warnings), 1)

    def test_ok(self):
        problems = [{"no": "1", "page": 1, "continues_next": False}]
        self.assertEqual(ingest.finalize(problems, 1), [])


if __name__ == "__main__":
    unittest.main()
