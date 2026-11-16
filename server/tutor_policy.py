#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""专业 tutor 教学策略层（P0）。

只做三件事：
1. 学生动作分类；
2. 教学状态推进；
3. 回复契约校验。

不直接调用模型，不读写数据库。
"""
import re

DISTRESS = (
    "进行不下去", "卡住", "卡在", "不懂", "不明白", "不太清楚", "不清楚",
    "没思路", "没头绪", "一无所知", "看不懂", "听不明白", "跟不上",
    "不会做", "不会写", "不会讲", "不会算", "不会证", "别问", "给提示",
)
# “不会 / 不知道”只有在说学生自己的状态时才算卡住。
# “会不会有……”“不会出现层高加一”“层高是不会变化的”是普通提问或陈述，
# 2026-11-15 复盘的 6 条 stuck 里有 3 条是这样误判的。
NOT_STUCK = re.compile(
    r"会不会|能不能|是不是|该不该|要不要"
    r"|不会(出现|变|影响|再|是|有|增加|减少|溢出|重复|一样|相等)"
)
SELF_STUCK = re.compile(
    r"(我|俺|咱|自己)[^，。？！,.?!]{0,6}(不会|不知道|不懂|不明白|不清楚|没懂|没听懂|没学会)"
    r"|(好像|感觉|确实|真的|反正)[^，。？！,.?!]{0,4}(不会|不知道|不懂)"
)
BARE_STUCK = re.compile(r"^(不会|不知道|不懂|不明白|不清楚)[。！!，,]*$")
FRUSTRATION = ("不想做", "烦死", "崩了", "放弃", "受不了", "没心情", "不想学")
EXPLAIN = ("直接讲", "给我完整解法", "别问了")
OFF_TOPIC = ("这题是不是考", "另一门", "题外")

ACTIONS = ("probe", "hint", "explain", "check", "advance", "close", "redirect", "pause")


def is_stuck(text):
    """判断学生是不是真的卡住。

    “不会出现层高加一”“那是会不会有……”是陈述/提问，不是卡住；
    只有“我不会”“不知道”“不会做”这类说自己状态的说法才算。
    """
    t = str(text or "").strip()
    if NOT_STUCK.search(t):
        return False
    if any(k in t for k in DISTRESS):
        return True
    if SELF_STUCK.search(t):
        return True
    return bool(BARE_STUCK.match(t))


def classify_move(text):
    t = str(text or "").strip()
    if any(k in t for k in FRUSTRATION):
        return "frustration"
    if is_stuck(t):
        return "stuck"
    if any(k in t for k in EXPLAIN):
        return "request_explain"
    if any(k in t for k in OFF_TOPIC):
        return "off_topic"
    if "懂了" in t or "明白了" in t or "会了" in t:
        return "claim_understanding"
    if "？" in t or "?" in t:
        return "question"
    if re.search(r"因为|所以|先|然后|最后|依次|依据", t):
        return "reason"
    return "answer"


def initial_state():
    return {
        "probes": 0,
        "hint_level": 0,
        "last_action": "none",
        "checked": False,
    }


def next_action(state, move):
    """返回 (action, new_state)。动作规则优先于模型。"""
    s = dict(initial_state())
    s.update(state or {})
    if move == "request_explain":
        s["probes"] = 0
        s["last_action"] = "explain"
        return "explain", s
    if move == "frustration":
        s["probes"] = 0
        s["last_action"] = "pause"
        return "pause", s
    if move == "stuck":
        s["hint_level"] = min(3, int(s["hint_level"]) + 1)
        s["probes"] = 0
        s["last_action"] = "hint"
        return "hint", s
    if move == "claim_understanding":
        s["probes"] = 0
        s["checked"] = True
        s["last_action"] = "check"
        return "check", s
    if move == "off_topic":
        s["probes"] = 0
        s["last_action"] = "redirect"
        return "redirect", s
    if move == "question":
        s["probes"] = 0
        s["last_action"] = "explain"
        return "explain", s
    if move == "reason":
        s["probes"] = 0
        s["last_action"] = "advance"
        return "advance", s
    # answer only
    if int(s["probes"]) >= 2 or int(s["hint_level"]) >= 1:
        s["hint_level"] = min(3, int(s["hint_level"]) + 1)
        s["probes"] = 0
        s["last_action"] = "hint"
        return "hint", s
    s["probes"] = int(s["probes"]) + 1
    s["last_action"] = "probe"
    return "probe", s


def sanitize_questions(text):
    """只保留第一个问句，防止一轮多问。"""
    s = str(text or "").strip()
    if not s:
        return s
    end = -1
    for i, ch in enumerate(s):
        if ch in "？?":
            end = i
            break
    if end < 0:
        return s
    first = s[:end + 1].strip()
    # 如果第一问前面只有很短的语气词，保留它；否则只留第一问
    return first


def style_flags(text):
    """人性化检查：奉承、空泛、多问号。"""
    t = str(text or "")
    flags = []
    if any(k in t for k in ("太棒了", "完美", "太聪明", "真厉害")):
        flags.append("praise")
    if any(k in t for k in ("再想想", "具体一点", "还有呢")):
        flags.append("vague")
    if t.count("？") + t.count("?") > 1:
        flags.append("multi_question")
    return flags


def validate_reply(action, text, state=None):
    """回复契约校验；不合格时调用方应兜底。"""
    if action not in ACTIONS:
        return False
    text = str(text or "").strip()
    if not text:
        return False
    state = state or {}
    if action == "probe":
        return text.count("？") + text.count("?") == 1
    if action == "hint":
        return ("提示" in text or "先看" in text or "线索" in text) and not text.endswith("？")
    if action == "check":
        return any(k in text for k in ("复述", "说说", "解释", "自己的话"))
    if action == "redirect":
        return any(k in text for k in ("回到", "这题", "先看题"))
    if action == "close":
        return bool(state.get("checked"))
    return True


def fallback_text(action, plan=None):
    """策略层兜底文本；不替学生写答案。"""
    plan = plan or {}
    if action == "hint":
        for s in plan.get("stuck") or []:
            hint = str(s.get("hint") or "").strip()
            nxt = str(s.get("next") or "").strip()
            if hint:
                out = "先停一下，不再重复追问。提示：" + hint
                if nxt:
                    out += " 下一步：" + nxt
                return out
        return "先停一下，不再重复追问。只做一步：用一句话说出题目里的操作顺序。"
    if action == "check":
        return "用你自己的话把这题的关键一步复述一遍。"
    if action == "redirect":
        return "先回到这道题：题目问的是什么？"
    if action == "pause":
        return "先停一下，这题现在不适合硬扛。你可以选：休息两分钟、只做一小步、或者换一道。"
    if action == "explain":
        return "可以，我先只讲你卡住的那一步，讲完你接一句。"
    return "先停一下，我们只推进一小步。"
