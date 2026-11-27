#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""讲题 agent loop：感知 → 决策 → 生成 → 校验 → 重试/兜底 → 落状态。

设计要点：
1. 规则优先于模型：决策层是确定性状态机（tutor_policy），
   LLM 只是被调用的生成工具；
2. generate 依赖注入：线上注入 speech.chat_reply，测试/重放注入假函数，
   所以本模块不直接调模型、不读写数据库、不碰 HTTP；
3. 契约校验闭环：生成结果不合格时，把契约要求反馈给模型重试（有限次），
   仍不合格就用策略层兜底话术，保证任何情况下都有合契约的回复。
"""
import tutor_policy

ACTION_PROMPTS = {
    "probe": {
        "prompt": (
            "本轮动作「追问」：学生正在往下讲但还没到位。只问一个能推动他继续想的问题，"
            "不讲解、不确认、不给提示、不替他说答案。回复恰好包含一个问句，1~3 句。"
        ),
        "contract": "本轮必须恰好包含一个问句；不讲解、不给提示、不替学生说答案。",
    },
    "hint": {
        "prompt": (
            "本轮动作「提示」：学生卡住了。给一个最小提示——只指向思考方向，不说出答案。"
            "回复里要出现「提示 / 先看 / 线索」这类字眼，不以问号结尾，说完留一步给学生。"
        ),
        "contract": "本轮回复必须包含「提示 / 先看 / 线索」且不以下问句结尾；不能直接给答案。",
    },
    "explain": {
        "prompt": (
            "本轮动作「讲解」：学生要求讲解或问了概念问题。只讲卡住的那一步、那一个点，"
            "不一次性展开整题解法，讲完留一句让学生接。"
        ),
        "contract": "只讲一步，不展开整题解法。",
    },
    "check": {
        "prompt": (
            "本轮动作「验证」：学生声称懂了。不要直接相信，请他用自己的话复述关键一步，"
            "以此区分真懂和背公式。回复里要出现「复述 / 用自己的话说说 / 解释」这类字眼。"
        ),
        "contract": "本轮必须要求学生用自己的话复述（出现「复述 / 说说 / 自己的话 / 解释」）。",
    },
    "redirect": {
        "prompt": (
            "本轮动作「拉回」：学生跑题了。温和地一句话拉回本题，问题目到底在问什么。"
            "回复里要出现「回到 / 这题 / 先看题」。"
        ),
        "contract": "本轮必须拉回本题（出现「回到 / 这题 / 先看题」）。",
    },
    "pause": {
        "prompt": (
            "本轮动作「暂停」：学生情绪受挫或不想做了。先接住情绪，再给两三个可选动作"
            "（休息两分钟 / 只做一小步 / 换一道题），不追问、不讲解、不硬推。"
        ),
        "contract": "暂停时不追问、不讲解，只给可选动作。",
    },
    "advance": {
        "prompt": (
            "本轮动作「推进」：学生在正常往下讲。只确认他刚讲的这一步，顺势承接，"
            "1~3 句，不展开讲解、不连问多个问题。"
        ),
        "contract": "只回应学生刚讲的这一步，1~3 句，不展开不连问。",
    },
    "close": {
        "prompt": (
            "本轮动作「收尾」：本题讲解已验证完成。确认学生的总结，准备进入收尾评级，"
            "不再展开新内容。"
        ),
        "contract": "确认收尾，不再展开新内容。",
    },
}


def build_action_prompt(action, state=None):
    """action → 本轮约束（注入 system 的 extra）+ 契约说明（校验失败时的反馈语）。"""
    info = ACTION_PROMPTS.get(action) or ACTION_PROMPTS["advance"]
    header = "【本轮教学动作】%s" % info["prompt"]
    return {"prompt": header, "contract": info["contract"]}


class TutorLoop:
    """一轮一调的讲题闭环控制器。

    generate(text, history, context, extra, meta) -> {"text": ..., "speech": ...}
    由调用方注入；本类不直接调模型。
    """

    def __init__(self, generate, max_retries=2):
        self._generate = generate
        self._max_retries = max(0, int(max_retries))

    def step(self, text, state=None, context="", history=None, plan=None, meta=None):
        """走一轮闭环，返回 {text, speech, state, trace, action, move}。"""
        text = str(text or "").strip()
        state = dict(tutor_policy.initial_state(), **(state or {}))
        history = history or []
        meta = meta or {}
        plan = plan or {}

        trace = {"move": None, "action": None, "attempts": 0, "valid": False, "fallback": False}

        move = tutor_policy.classify_move(text)
        action, state = tutor_policy.next_action(state, move)
        trace["move"] = move
        trace["action"] = action

        brief = build_action_prompt(action, state)
        extra = brief["prompt"]
        reply = ""
        speech = ""

        for attempt in range(self._max_retries + 1):
            trace["attempts"] = attempt + 1
            try:
                r = self._generate(text, history, context, extra, meta) or {}
            except Exception as e:  # 模型调用失败：不重试，直接兜底，保证有回复
                trace["error"] = str(e)
                break
            reply = str(r.get("text") or "").strip()
            speech = str(r.get("speech") or "").strip() or reply
            if tutor_policy.validate_reply(action, reply, state):
                trace["valid"] = True
                break
            extra += "\n\n【上一条不合格】%s 请按动作要求重写。" % brief["contract"]

        if not trace["valid"]:
            reply = tutor_policy.fallback_text(action, plan)
            speech = reply
            trace["fallback"] = True

        state["engine"] = "loop"
        return {
            "text": reply,
            "speech": speech,
            "state": state,
            "trace": trace,
            "action": action,
            "move": move,
        }
