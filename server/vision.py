#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qwen-VL 试卷切题：单页识别 + bbox 归一化。

不依赖第三方 SDK；使用 DashScope OpenAI 兼容接口。
"""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request

import usage_log

API = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
MODEL = os.environ.get("TUTOR_VL_MODEL", "qwen3-vl-plus")


def get_key():
    key = (os.environ.get("DASHSCOPE_API_KEY") or "").strip()
    if key:
        return key
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
                return str(winreg.QueryValueEx(k, "DASHSCOPE_API_KEY")[0] or "").strip()
        except OSError:
            pass
    return ""


def normalize_bbox(bbox, width, height):
    """模型有时给像素、有时给 0~1；统一成 0~1，并夹到图内。"""
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    vals = []
    for v in bbox:
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            return None
    if max(vals) > 1.5:
        vals = [vals[0] / width, vals[1] / height, vals[2] / width, vals[3] / height]
    x1, y1, x2, y2 = vals
    x1, x2 = sorted((max(0.0, min(1.0, x1)), max(0.0, min(1.0, x2))))
    y1, y2 = sorted((max(0.0, min(1.0, y1)), max(0.0, min(1.0, y2))))
    if x2 - x1 < 0.01 or y2 - y1 < 0.005:
        return None
    return [round(x1, 5), round(y1, 5), round(x2, 5), round(y2, 5)]


def _prompt(prev, subject="math2"):
    extra = ""
    if prev:
        opts = "".join(o.get("label", "") for o in (prev.get("options") or []))
        extra = (
            "上一页最后一题是第 %s 题，已识别选项：%s。"
            "如果本页顶部有属于它的无题号续块（例如 C/D 选项），必须放进 leading_continuation。"
            % (prev.get("no"), opts or "无")
        )
    if subject == "cs408":
        return (
            "你是 408 计算机统考试卷切题助手。识别整页试卷，按题号切分，输出严格 JSON，不要 Markdown。\n"
            "结构：第 1~40 题为单项选择题，每题必须有题干和 A/B/C/D 四个选项；"
            "第 41~47 题为综合应用题，一个大题只输出一个 problem，题干里保留 (1)(2)(3) 全部小问，"
            "不要把小问拆成独立题目；没有选项就输出空数组。\n"
            "JSON 结构：{\"problems\":[{\"no\":\"1\",\"type\":\"single\",\"text\":\"题干文字\","
            "\"options\":[{\"label\":\"A\",\"text\":\"选项内容\"}],\"latex\":\"\","
            "\"bbox\":[x1,y1,x2,y2],\"continues_next\":false}],"
            "\"leading_continuation\":{\"text\":\"页面顶部无题号的续块\","
            "\"options\":[{\"label\":\"C\",\"text\":\"选项内容\"}],"
            "\"bbox\":[x1,y1,x2,y2],\"continues_prev\":true}}\n"
            "41~47 题的 type 填 comprehensive，其余填 single。\n"
            "一页通常只有 3~8 题；只按页面上独立题号切分，题号必须连续、不重复。"
            "不要把 A/B/C/D 选项、小问 (1)(2)、共享说明（如“题 33~41 均依据下图”）当成新题。\n"
            "题干里有图/表时，在 text 里写“[图/表见原题]”，bbox 必须覆盖图和表；不要把图里的字猜成题干。\n"
            + extra +
            "没有顶部续块时 leading_continuation 填 null。\n"
            "bbox 用 0~1 相对坐标，覆盖从题号到最后一个选项/小问的整块；跨页题在页尾标 continues_next=true；只输出 JSON。"
        )
    return (
        "你是数学试卷切题助手。识别整页试卷，按题号切分，输出严格 JSON，不要 Markdown。\n"
        "每题必须包含题干和 A/B/C/D 四个选项（如果有），不要把选项漏掉。\n"
        "JSON 结构：{\"problems\":[{\"no\":\"1\",\"text\":\"题干文字\",\"options\":[{\"label\":\"A\",\"text\":\"选项内容\"}],"
        "\"latex\":\"题干公式的 LaTeX（没有就空字符串）\",\"bbox\":[x1,y1,x2,y2],\"continues_next\":false}],"
        "\"leading_continuation\":{\"text\":\"页面顶部无题号的续块\",\"options\":[{\"label\":\"C\",\"text\":\"选项内容\"}],"
        "\"bbox\":[x1,y1,x2,y2],\"continues_prev\":true}}\n"
        + extra +
        "没有顶部续块时 leading_continuation 填 null。\n"
        "bbox 用 0~1 相对坐标，覆盖从题号到最后一个选项的整块；跨页题在页尾标 continues_next=true；只输出 JSON。"
    )


def _json(content):
    """模型偶尔把 LaTeX 反斜杠写成单反斜杠，先修再解析。"""
    try:
        return json.loads(content, strict=False)
    except json.JSONDecodeError:
        fixed = re.sub(r'\\(?![\\"/bfnrtu])', r'\\\\', content)
        try:
            return json.loads(fixed, strict=False)
        except json.JSONDecodeError as e:
            raise RuntimeError("切题 JSON 解析失败：%s；片段：%s" % (e, content[max(0, e.pos - 80):e.pos + 80]))


def segment(image_path, prev=None, model=MODEL, subject="math2"):
    from PIL import Image
    key = get_key()
    if not key:
        raise RuntimeError("缺少 DASHSCOPE_API_KEY")
    with Image.open(image_path) as im:
        width, height = im.size
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    body = {
        "model": model,
        "temperature": 0,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": _prompt(prev, subject)},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
            ],
        }],
    }
    data = _post(body)
    content = _content(data)
    obj = _json(content)
    problems = obj.get("problems") or []
    for p in problems:
        p["bbox"] = normalize_bbox(p.get("bbox"), width, height)
        p["page_size"] = [width, height]
    lead = obj.get("leading_continuation")
    if isinstance(lead, dict):
        lead["bbox"] = normalize_bbox(lead.get("bbox"), width, height)
    else:
        lead = None
    return {
        "problems": problems,
        "leading_continuation": lead,
        "usage": data.get("usage", {}),
        "image_size": [width, height],
    }


def identify_leading(image_path, first_problem_bbox, prev_no):
    """两遍法的第二遍：裁出第一题上方的窄条，专门问“是不是上一题的续块”。

    整页模型经常把顶部 C/D 选项吞掉；窄条只含这一小块，识别更稳。
    """
    from PIL import Image
    import io
    top = first_problem_bbox[1] if first_problem_bbox else 1.0
    if top <= 0.02:
        return None
    with Image.open(image_path) as im:
        w, h = im.size
        y2 = max(1, int((top - 0.002) * h))
        strip = im.crop((0, 0, w, y2)).convert("RGB")
        buf = io.BytesIO()
        strip.save(buf, format="JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    prompt = (
        "这是数学试卷一页顶部的一小段，可能属于上一页最后一题（第 %s 题）。\n"
        "识别这段里的文字和选项。输出严格 JSON，不要 Markdown："
        "{\"belongs_to_previous\":true,\"text\":\"这段文字\",\"options\":[{\"label\":\"C\",\"text\":\"选项内容\"}]}\n"
        "如果它只是页眉、页码、新题开头或无关内容，belongs_to_previous 填 false。只输出 JSON。"
        % prev_no
    )
    body = {
        "model": MODEL,
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
        ]}],
    }
    data = _post(body)
    obj = json.loads(_content(data))
    if not obj.get("belongs_to_previous"):
        return None
    obj["source"] = "strip"
    obj["bbox"] = [0.0, 0.0, 1.0, round(top, 5)]
    return obj


def describe_figure(image_path, model=MODEL, focus=""):
    """只描述题图/图形结构，不解题。"""
    key = get_key()
    if not key:
        raise RuntimeError("缺少 DASHSCOPE_API_KEY")
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    prompt = (
        "这是试卷图片。只描述与指定题目有关的图形、树、表格或标注结构，帮助一个看不见图的老师理解题目。"
        "不要解题，不要给答案。不要描述页面上的其他题目。"
        "说明：有哪些元素、它们之间的连接/层级/位置关系、图中文字和标注。用一段中文，尽量具体。"
    )
    if focus:
        prompt += "\n指定题目：" + str(focus)[:600]
    body = {
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
        ]}],
    }
    data = _post(body)
    return _content(data).strip()


def read_problem(image_path, model=MODEL):
    """只读一道题：返回 {text, options, latex}，用于「重读此题」。"""
    from PIL import Image
    key = get_key()
    if not key:
        raise RuntimeError("缺少 DASHSCOPE_API_KEY")
    with Image.open(image_path) as im:
        width, height = im.size
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    prompt = (
        "这是单道数学题的图片。只识别这一道题，输出严格 JSON，不要 Markdown：\n"
        "{\"text\":\"题干文字\",\"options\":[{\"label\":\"A\",\"text\":\"选项内容\"}],"
        "\"latex\":\"题干公式的 LaTeX（没有就空字符串）\"}\n"
        "公式用 LaTeX；选项没有就返回空数组；不要输出其他内容。"
    )
    body = {
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
        ]}],
    }
    data = _post(body)
    obj = json.loads(_content(data))
    return {
        "text": str(obj.get("text") or ""),
        "options": obj.get("options") if isinstance(obj.get("options"), list) else [],
        "latex": str(obj.get("latex") or ""),
        "usage": data.get("usage", {}),
        "image_size": [width, height],
    }


def _content(data):
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    return content.strip()


def _post(body):
    key = get_key()
    if not key:
        raise RuntimeError("缺少 DASHSCOPE_API_KEY")
    req = urllib.request.Request(
        API, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        method="POST",
    )
    try:
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    data = json.loads(r.read().decode("utf-8"))
                    usage_log.log("vision", body.get("model") or MODEL, usage=data.get("usage") or {})
                    return data
            except (TimeoutError, urllib.error.URLError):
                if attempt == 1:
                    raise
                time.sleep(3)
    except urllib.error.HTTPError as e:
        raise RuntimeError("HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:500]))
