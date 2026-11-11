#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整卷切题管线：多页 → Qwen-VL → 跨页合并 → bbox 裁图 → 预览 HTML。

用法：
  python ingest.py ../samples/page1.jpg ../samples/page2.jpg
"""
import datetime
import html
import json
import os
import shutil
import sys

from PIL import Image

import vision


def merge_leading(prev, lead, replace_conflicts=False):
    """把下一页顶部的无题号续块并回上一题；返回冲突/新增说明。"""
    if not prev or not lead:
        return {"merged": False}
    added, replaced, conflicts = [], [], []
    existing = {}
    for opt in (prev.get("options") or []):
        existing[str(opt.get("label", "")).upper()] = opt
    for opt in (lead.get("options") or []):
        label = str(opt.get("label", "")).upper()
        new = str(opt.get("text") or "").strip()
        if not label or not new:
            continue
        if label in existing:
            old = str(existing[label].get("text") or "").strip()
            if old and old != new:
                conflicts.append(label)
                if replace_conflicts:
                    existing[label]["text"] = opt.get("text")
                    replaced.append(label)
            continue
        prev.setdefault("options", []).append(opt)
        existing[label] = opt
        added.append(label)
    text = str(lead.get("text") or "").strip()
    if text and not (lead.get("options") or []):
        prev["continuation_text"] = (prev.get("continuation_text") or "") + ("\n" if prev.get("continuation_text") else "") + text
    prev.setdefault("page_fragments", []).append({"page": lead.get("page"), "bbox": lead.get("bbox"), "options": added, "replaced": replaced})
    prev["continues_next"] = False
    prev["merged_from_next"] = True
    if conflicts:
        prev.setdefault("option_conflicts", []).extend(conflicts)
    return {"merged": True, "added_options": added, "replaced_options": replaced, "conflicts": conflicts, "text": bool(text)}


def finalize(problems, page_count):
    """收尾：最后一页仍标跨页的，清掉并记录；中间页缺续块的给出警告。"""
    warnings = []
    for p in problems:
        # 模型偶尔给空选项/重复选项；清掉，回退到原图
        had_opts = len(p.get("options") or []) >= 2
        seen = set()
        clean = []
        for o in (p.get("options") or []):
            label = str(o.get("label", "")).upper()
            text = str(o.get("text") or "").strip()
            if not label or not text or label in seen:
                continue
            seen.add(label)
            clean.append(o)
        p["options"] = clean
        if had_opts and len(clean) < 2:
            warnings.append("第 %s 题选项不完整，讲题时以原图裁剪为准" % p.get("no"))
    for i, p in enumerate(problems):
        if not p.get("continues_next"):
            continue
        next_page = p.get("page", 1) + 1
        nxt = problems[i + 1] if i + 1 < len(problems) else None
        if p.get("page", 1) >= page_count or not nxt:
            p["continues_next"] = False
            p["auto_cleared"] = True
            warnings.append("第 %s 题原标跨页，但已是最后一页，已自动取消" % p.get("no"))
        elif nxt.get("page", 0) <= next_page:
            p["continues_next"] = False
            warnings.append("第 %s 题标了跨页，但下一页没有识别到续块，已自动取消" % p.get("no"))
    return warnings


def crop_boundary(problems, i):
    """返回第 i 题裁剪的下边界：下一题上边界再回收 0.0015，避免把下一题带进来。"""
    p = problems[i]
    if i + 1 >= len(problems):
        return None
    nxt = problems[i + 1]
    if nxt.get("page") != p.get("page"):
        return None
    a = (p.get("bbox") or [None])[1]
    b = (nxt.get("bbox") or [None])[1]
    if a is None or b is None or b <= a + 0.002:
        return None
    # 模型给的下边界经常压到下一题；留一点空隙，但不切掉本题文字
    gap = 0.006
    return round(b - gap, 5)


def _text_top_before(src, x1, x2, y_limit, y_start):
    """从下一题 bbox 上边界往上扫，找到下一题第一行文字，裁在其上方。

    手机照片有透字/噪点，用“暗像素比例 > 1%”判定文字行。
    """
    try:
        with Image.open(src) as im:
            g = im.convert("L")
            w, h = g.size
            left = max(0, int(min(x1, x2) * w))
            right = min(w, int(max(x1, x2) * w))
            if right - left < 20:
                return None
            top = max(0, int(y_start * h))
            start = min(h - 1, int(y_limit * h))
            for row in range(start, top, -1):
                strip = g.crop((left, row, right, row + 1))
                vals = list(strip.getdata())
                dark = sum(1 for v in vals if v < 120) / max(1, len(vals))
                if dark > 0.01:
                    return max(y_start + 0.002, row / h - 0.004)
    except Exception:
        return None
    return None


def crop_problem(src, bbox, out_path, pad=0.004, y2_limit=None):
    with Image.open(src) as im:
        w, h = im.size
        x1, y1, x2, y2 = bbox
        bottom_pad = pad * 0.3
        if y2_limit is not None and y2_limit > y1:
            auto = _text_top_before(src, x1, x2, y2_limit, y1)
            if auto:
                y2_limit = min(y2_limit, auto)
            y2 = min(y2, y2_limit)
            bottom_pad = 0
        box = (max(0, int((x1 - pad) * w)), max(0, int((y1 - pad) * h)),
               min(w, int((x2 + pad) * w)), min(h, int((y2 + bottom_pad) * h)))
        im.crop(box).convert("RGB").save(out_path, quality=90)


def write_preview(out_dir, pages, problems):
    rows = []
    for idx, p in enumerate(problems, 1):
        opts = "".join(
            '<div class="opt"><b>%s.</b> %s</div>' % (html.escape(str(o.get("label", ""))), html.escape(str(o.get("text", ""))))
            for o in (p.get("options") or [])
        )
        crop = "crops/p%02d.jpg" % idx
        frags = "".join(
            '<img class="frag" src="%s" alt="续块">' % html.escape(str(f.get("crop")))
            for f in (p.get("page_fragments") or []) if f.get("crop")
        )
        rows.append(
            '<section><div class="head"><b>第 %s 题</b><span>%s</span></div>'
            '<img src="%s">%s<div class="text">%s</div>%s</section>'
            % (html.escape(str(p.get("no", ""))), "跨页已合并" if p.get("merged_from_next") else "",
               crop, frags, html.escape(str(p.get("text", ""))), opts)
        )
    page_imgs = "".join('<figure><img src="pages/page-%02d.jpg"><figcaption>第 %d 页</figcaption></figure>' % (i, i) for i in range(1, pages + 1))
    doc = """<!doctype html><meta charset="utf-8"><title>切题预览</title>
<style>body{font-family:system-ui,"Microsoft YaHei",sans-serif;margin:24px;background:#f5f6f8;color:#111}
h1{font-size:20px}section{background:#fff;border:1px solid #ddd;border-radius:12px;padding:14px;margin:14px 0;max-width:980px}
.head{display:flex;gap:10px;align-items:baseline;margin-bottom:8px}.head span{color:#059669;font-size:12px}
img{max-width:100%%;border:1px solid #eee;border-radius:8px}.text{white-space:pre-wrap;line-height:1.7;margin:8px 0}
img.frag{max-width:62%%;border-color:#f59e0b;margin:6px 0}
.opt{margin:3px 0;line-height:1.5}figure{display:inline-block;vertical-align:top;width:46%%;margin:0 2%% 12px 0}
figcaption{font-size:12px;color:#666}</style>
<h1>切题预览（%d 页 / %d 题）</h1>%s<hr>%s</body>""" % (pages, len(problems), "".join(rows), page_imgs)
    path = os.path.join(out_dir, "preview.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path


def main():
    if len(sys.argv) < 2:
        print("用法：python ingest.py 图片1 图片2 ...")
        return 2
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    subject = os.environ.get("PAPER_SUBJECT", "math2")
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples", "ingest-" + stamp)
    os.makedirs(os.path.join(out_dir, "pages"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "crops"), exist_ok=True)

    problems = []
    warnings = []
    usages = []
    page_paths = []
    for page_no, src in enumerate(sys.argv[1:], 1):
        page_copy = os.path.join(out_dir, "pages", "page-%02d.jpg" % page_no)
        shutil.copyfile(src, page_copy)
        page_paths.append(page_copy)
        prev = problems[-1] if problems else None
        print("识别第 %d 页 …" % page_no)
        res = vision.segment(src, prev=prev, subject=subject)
        usages.append(res.get("usage", {}))
        lead = res.get("leading_continuation")
        # 每一页顶部都单独看一次：整页模型经常吞掉 C/D，甚至自己编选项
        if page_no > 1 and problems:
            first = (res.get("problems") or [None])[0]
            if first and first.get("bbox"):
                try:
                    strip_lead = vision.identify_leading(src, first["bbox"], problems[-1].get("no"))
                    if strip_lead:
                        lead = strip_lead
                        if not problems[-1].get("continues_next"):
                            warnings.append("第 %d 页顶部续块属于第 %s 题，模型未标跨页，已合并" % (page_no, problems[-1].get("no")))
                except Exception as e:
                    warnings.append("第 %d 页顶部续块识别失败：%s" % (page_no, e))
        if lead and problems:
            lead["page"] = page_no
            info = merge_leading(problems[-1], lead, replace_conflicts=True)
            if info.get("merged"):
                print("  续块已合并到第 %s 题：+%s" % (problems[-1].get("no"), "".join(info.get("added_options") or [])))
        elif lead:
            warnings.append("第 %d 页顶部有续块，但没有上一题可合并" % page_no)
        for p in res.get("problems") or []:
            p["page"] = page_no
            p["page_image"] = os.path.relpath(page_copy, out_dir)
            problems.append(p)
        print("  本页 %d 题" % len(res.get("problems") or []))

    warnings += finalize(problems, len(page_paths))
    os.makedirs(os.path.join(out_dir, "frags"), exist_ok=True)
    for i, p in enumerate(problems, 1):
        for j, frag in enumerate(p.get("page_fragments") or [], 1):
            if not frag.get("bbox") or not frag.get("page"):
                continue
            frag_path = os.path.join(out_dir, "frags", "p%02d-f%d.jpg" % (i, j))
            try:
                crop_problem(page_paths[frag["page"] - 1], frag["bbox"], frag_path, pad=0)
                frag["crop"] = os.path.relpath(frag_path, out_dir)
            except Exception as e:
                warnings.append("第 %s 题续块裁图失败：%s" % (p.get("no"), e))
    for i, p in enumerate(problems, 1):
        crop = os.path.join(out_dir, "crops", "p%02d.jpg" % i)
        if p.get("bbox"):
            try:
                crop_problem(page_paths[p["page"] - 1], p["bbox"], crop, y2_limit=crop_boundary(problems, i - 1))
                p["crop"] = os.path.relpath(crop, out_dir)
            except Exception as e:
                warnings.append("第 %s 题裁图失败：%s" % (p.get("no"), e))
        p.pop("page_image", None)

    result = {"pages": len(page_paths), "problems": problems, "warnings": warnings, "usage": usages}
    with open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    preview = write_preview(out_dir, len(page_paths), problems)
    print("完成：%d 题，警告 %d 条" % (len(problems), len(warnings)))
    for w in warnings:
        print("  ! " + w)
    print("结果：" + os.path.join(out_dir, "result.json"))
    print("预览：" + preview)
    return 0


if __name__ == "__main__":
    sys.exit(main())
