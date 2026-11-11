#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多科目 / 多场景教学约束矩阵（P1 设计层）。

只返回约束，不调用模型、不写数据库。
"""
SUBJECTS = {
    "math2": {
        "label": "数二",
        "focus": "步骤、依据、等价变形",
        "max_probes": 2,
        "must": "每一步为什么可以这样做",
        "avoid": "跳步、只报答案",
    },
    "english2": {
        "label": "英二",
        "focus": "题干关键词、原文证据、干扰项",
        "max_probes": 1,
        "must": "先定位证据，再解释为什么排除",
        "avoid": "逐句翻译全文、只靠关键词匹配",
    },
    "cs408": {
        "label": "408",
        "focus": "题目条件、结构/算法、边界与复杂度",
        "max_probes": 2,
        "must": "排除项要有理由，不能只凭名字",
        "avoid": "把选择题讲成大题、忽略边界",
    },
    "writing": {
        "label": "写作",
        "focus": "任务覆盖、结构、语言硬伤",
        "max_probes": 0,
        "must": "must_fix 最多一条根因",
        "avoid": "代写、无限润色、打分代替修改",
    },
}

SITUATIONS = {
    "answer_only": {"action": "probe", "max_probes": 1, "note": "只报答案，先问依据"},
    "reason": {"action": "advance", "max_probes": 0, "note": "有依据就推进"},
    "stuck": {"action": "hint", "max_probes": 0, "note": "卡住先给提示，不再问"},
    "fake_understanding": {"action": "check", "max_probes": 0, "note": "假懂必须复述/迁移"},
    "frustration": {"action": "hint", "max_probes": 0, "note": "先降难度/暂停，不追问"},
    "off_topic": {"action": "redirect", "max_probes": 0, "note": "先回题"},
    "review": {"action": "probe", "max_probes": 1, "note": "复述优先，提示后置"},
    "exam": {"action": "hint", "max_probes": 0, "note": "考试模式只给最小提示"},
}

MOVE_TO_SITUATION = {
    "answer": "answer_only",
    "reason": "reason",
    "stuck": "stuck",
    "frustration": "frustration",
    "request_explain": "answer_only",
    "claim_understanding": "fake_understanding",
    "off_topic": "off_topic",
}


def situation_for(move, mode="tutor"):
    """模式优先：review/exam 覆盖普通讲题场景。"""
    mode = str(mode or "tutor")
    if mode == "review":
        return "review"
    if mode == "exam":
        return "exam"
    return MOVE_TO_SITUATION.get(str(move or ""), "answer_only")



def policy_for(subject, situation):
    sub = SUBJECTS.get(str(subject or ""), SUBJECTS["math2"])
    sit = SITUATIONS.get(str(situation or ""), SITUATIONS["answer_only"])
    max_probes = min(sub["max_probes"], sit["max_probes"]) if sit["action"] == "probe" else 0
    return {
        "subject": subject,
        "situation": situation,
        "label": sub["label"],
        "focus": sub["focus"],
        "must": sub["must"],
        "avoid": sub["avoid"],
        "action": sit["action"],
        "max_probes": max_probes,
        "note": sit["note"],
    }
