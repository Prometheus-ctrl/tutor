#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""不重新调 API，按现有 result.json 重算裁剪和预览。

用法：python reprocess.py ..\samples\ingest-日期-时间
"""
import json
import os
import sys

import ingest


def main():
    if len(sys.argv) < 2:
        print("用法：python reprocess.py samples/ingest-...")
        return 2
    out_dir = os.path.abspath(sys.argv[1])
    with open(os.path.join(out_dir, "result.json"), encoding="utf-8") as f:
        result = json.load(f)
    problems = result["problems"]
    pages = result["pages"]
    page_paths = [os.path.join(out_dir, "pages", "page-%02d.jpg" % i) for i in range(1, pages + 1)]
    for i, p in enumerate(problems):
        path = os.path.join(out_dir, "crops", "p%02d.jpg" % (i + 1))
        if p.get("bbox") and os.path.exists(page_paths[p["page"] - 1]):
            ingest.crop_problem(page_paths[p["page"] - 1], p["bbox"], path, y2_limit=ingest.crop_boundary(problems, i))
            p["crop"] = os.path.relpath(path, out_dir)
    with open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    preview = ingest.write_preview(out_dir, pages, problems)
    print("已重算裁剪：%d 题" % len(problems))
    print("预览：" + preview)
    return 0


if __name__ == "__main__":
    sys.exit(main())
