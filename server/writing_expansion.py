#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字数不足时的具体扩写建议。

只给“加在哪、加什么、预计多少词、句首提示”，不写完整段落。
"""
import re

DATA_RE = re.compile(r"\d+(?:\.\d+)?\s*%")
CAUSE_RE = re.compile(r"\b(because|since|due to|reason|factor|account for|result from|first|second)\b", re.I)
EXAMPLE_RE = re.compile(r"\b(for example|for instance|such as|like)\b", re.I)
COMMENT_RE = re.compile(r"\b(in my view|in my opinion|i think|should|need|future|however|therefore)\b", re.I)


def _slot(where, what, words, starter):
    return {"where": where, "what": what, "words": words, "starter": starter}


def expansion_advice(part, draft, target, chart_data=None):
    """返回 2-3 个内容槽位，使预计增加词数能覆盖缺口。"""
    text = str(draft or "")
    words = len(re.findall(r"[A-Za-z]+(?:['-][A-Za-z]+)?", text))
    need = max(0, int(target) - words)
    slots = []
    if str(part).upper().startswith("A"):
        slots.append(_slot("主体段", "把每条 bullet 补成“谁/什么/何时/哪里/为什么/怎么做”", 20, "For example, ..."))
        slots.append(_slot("主体段", "给一个建议或安排补具体理由/例子", 20, "The reason is that ..."))
        slots.append(_slot("结尾", "补期待回复、感谢或下一步", 15, "I look forward to ..."))
    else:
        numbers = DATA_RE.findall(text)
        if not CAUSE_RE.search(text):
            slots.append(_slot("第二段", "补一个原因，说明为什么会出现这个趋势", 25, "One reason is that ..."))
        if not EXAMPLE_RE.search(text):
            slots.append(_slot("第二段", "给原因补一个具体例子/机制", 20, "For instance, ..."))
        if not COMMENT_RE.search(text):
            slots.append(_slot("第三段", "补一句评论、限制或建议，不只做预测", 15, "In my view, ..."))
        if (len(numbers) < 2 or sum(s["words"] for s in slots) < need) and len(slots) < 3:
            slots.append(_slot("第一段", "补一个中间年份的数据点或前后对比", 20, "In 20xx, the figure was ..."))
        if len(slots) < 2:
            slots.append(_slot("第三段", "补一个对比或限制，避免只重复第一段", 15, "However, ..."))
    # 按缺口截取，最多 3 个；不够就保留全部
    out = []
    total = 0
    for s in slots[:3]:
        out.append(s)
        total += s["words"]
        if total >= need and len(out) >= 2:
            break
    return out


def format_advice(slots, target):
    if not slots:
        return "补到约 %d 词，先补题目要求的内容。" % target
    parts = []
    for s in slots:
        parts.append("%s：%s（约 +%d 词，句首：%s）" % (s["where"], s["what"], s["words"], s["starter"]))
    return "补到约 %d 词。可加：%s" % (target, "；".join(parts))
