#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""语音链路：Qwen3-ASR / DeepSeek 讲题 / Qwen3-TTS。

ASR 用 base64 data URL，避免“必须公网可访问音频 URL”的限制。
TTS 返回的临时 URL 由服务端下载后本地提供，避免浏览器跨域/过期。
"""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import prompt_loader
from vision import get_key
import local_tts
import usage_log
import writing_expansion

DASHSCOPE = "https://dashscope.aliyuncs.com"
ASR_URL = DASHSCOPE + "/api/v1/services/aigc/multimodal-generation/generation"
CHAT_URL = DASHSCOPE + "/compatible-mode/v1/chat/completions"
TTS_URL = DASHSCOPE + "/api/v1/services/aigc/multimodal-generation/generation"
ASR_MODEL = os.environ.get("TUTOR_ASR_MODEL", "qwen3-asr-flash")
CHAT_MODEL = os.environ.get("TUTOR_CHAT_MODEL", "qwen-plus")
TTS_MODEL = os.environ.get("TUTOR_TTS_MODEL", "qwen3-tts-flash")
TTS_VOICE = os.environ.get("TUTOR_TTS_VOICE", "Cherry")
TTS_PROVIDER = os.environ.get("TUTOR_TTS_PROVIDER", "cloud").strip().lower()
TTS_LOCAL_URL = os.environ.get("TUTOR_TTS_LOCAL_URL", "http://127.0.0.1:8794").rstrip("/")

DEEPSEEK_URL = os.environ.get("TUTOR_DEEPSEEK_URL", "https://api.deepseek.com/chat/completions")
DEEPSEEK_KEY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "deepseek.key"
)

# JSON 字符串里合法的单字符转义；LaTeX 的 \(...\)、\frac 不在此列
_BAD_JSON_ESCAPE = re.compile(r'(?<!\\)\\(?![\\"/bfnrtu])')


def parse_model_json(raw):
    """从模型回复里取出 JSON 对象。

    模型有时在 JSON 字符串里直接写 LaTeX（\\(...\\)、\\frac），反斜杠没转义，
    这不是合法 JSON。先按原文解析；失败就把非法反斜杠补成双反斜杠再试一次。
    """
    text = str(raw or "").strip()
    m = re.search(r"\{[\s\S]*\}", text)
    body = m.group(0) if m else text
    fixed = _BAD_JSON_ESCAPE.sub(lambda _m: "\\\\", body)
    for candidate in (body, fixed):
        try:
            obj = json.loads(candidate, strict=False)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None

CHAT_MODELS = {
    "deepseek-flash": {"provider": "deepseek", "model": "deepseek-flash", "label": "DeepSeek V4.1 Flash"},
    "deepseek-v4-pro": {"provider": "deepseek", "model": "deepseek-v4-pro", "label": "DeepSeek V4 Pro"},
    "qwen-plus": {"provider": "qwen", "model": "qwen-plus", "label": "Qwen Plus"},
    "qwen-max": {"provider": "qwen", "model": "qwen-max", "label": "Qwen Max"},
}
NORMALIZE_MODEL = os.environ.get("TUTOR_NORMALIZE_MODEL", "qwen-plus")
FINISH_MODEL = os.environ.get("TUTOR_FINISH_MODEL", "qwen-plus")


def deepseek_key():
    key = (os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("TUTOR_DEEPSEEK_KEY") or "").strip()
    if key:
        return key
    try:
        with open(DEEPSEEK_KEY_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def chat_provider():
    forced = (os.environ.get("TUTOR_CHAT_PROVIDER") or "").strip().lower()
    if forced in ("deepseek", "qwen"):
        return forced
    return "deepseek" if deepseek_key() else "qwen"


SYSTEM_PROMPT = (
    "你是数学题的苏格拉底教练。学生正在口述一道题的解题思路。\n"
    "规则：\n"
    "1. 先听完，不急着给答案；一次只问一个问题。\n"
    "2. 只在学生明确说卡住、前后矛盾、或关键步骤含糊时追问。\n"
    "3. 如果学生概念错/忘，先用一两句话讲清概念，再让他复述。\n"
    "4. 不要把完整解法直接倒出来；除非学生明确说“直接讲”。\n"
    "5. 学生只报选项/答案（如“选 C”“等于 1”）时，不要确认他已经讲完；先问依据。\n"
    "6. 不许说“你已经讲完了”“可以确认”“这题就到这里”这类结案话；是否结束由学生点按钮决定。\n"
    "7. 不要替学生总结整题，也不要重复他已经确认过的结论；一次只推进一个点。\n"
    "8. 学生说“对/好/嗯”时，追问下一步或一个关键依据，不要把刚才的内容再复述一遍。\n"
    "9. 不要使用 Markdown（不要 **、#、- 列表、表格）。\n"
    "10. 必须严格输出两段，用下面的标记，不要输出其他内容：\n"
    "【显示】\n"
    "给屏幕看的版本。涉及的公式必须用 LaTeX 写出来，行内用 \\( ... \\)，独立公式用 \\[ ... \\]。\n"
    "【朗读】\n"
    "给语音朗读的版本。纯口语，公式用中文说，例如：a 等于 f(x) 除以 x，当 x 趋于无穷时的极限。不要出现 LaTeX、$、\\(、\\)、**。\n"
    "两段内容意思一致，但显示版可以更结构化，朗读版要短句、多逗号。"
)


def split_reply(raw):
    """把模型输出拆成屏幕版/朗读版；格式不合法时回退。"""
    text = str(raw or "").strip()
    m = re.search(r"【显示】\s*(.*?)\s*【朗读】\s*(.*)", text, re.S)
    if m:
        display = m.group(1).strip()
        speech = m.group(2).strip()
        if display and speech:
            return display, speech
    return text, spoken_text(text)



def spoken_text(text):
    """把回复改成适合 TTS 朗读的中文口语，去掉 Markdown/LaTeX 符号。"""
    s = str(text or "")
    for _ in range(2):
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = re.sub(r"\*(.+?)\*", r"\1", s)
        s = re.sub(r"`([^`]*)`", r"\1", s)
        s = re.sub(r"\$\$(.+?)\$\$", r"\1", s)
        s = re.sub(r"\$(.+?)\$", r"\1", s)
        s = re.sub(r"\\\((.+?)\\\)", r"\1", s)
        s = re.sub(r"\\\[(.+?)\\\]", r"\1", s)
    s = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"\1 除以 \2", s)
    s = re.sub(r"\\sqrt\{([^{}]+)\}", r"根号 \1", s)
    s = s.replace("\\lim", "极限").replace("\\infty", "无穷").replace("\\to", "趋于")
    s = s.replace("\\", "")
    table = {
        "∞": "无穷", "→": "趋于", "≤": "小于等于", "≥": "大于等于",
        "≠": "不等于", "×": "乘以", "÷": "除以", "±": "正负",
        "∈": "属于", "∑": "求和", "∫": "积分", "√": "根号",
        "π": "派", "α": "阿尔法", "β": "贝塔", "θ": "西塔",
        "lim": "极限", "=": "等于", "+": "加", "/": "除以",
    }
    for a, b in table.items():
        s = s.replace(a, b)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()



def _post(url, body, key=None, timeout=180):
    key = key or get_key()
    if not key:
        raise RuntimeError("缺少 API key")
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError("HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:500]))
    except urllib.error.URLError as e:
        host = urllib.parse.urlparse(url).hostname or url
        reason = getattr(e, "reason", e)
        raise RuntimeError(
            "连不上 %s：%s。检查网络；如果刚换过代理/VPN，重启讲伴（或关掉代理）再试。" % (host, reason)
        )


def wav_seconds(path):
    """粗略算 WAV 时长（秒），用于 ASR 费用估算。"""
    try:
        with open(path, "rb") as f:
            data = f.read()
        i = data.find(b"fmt ")
        j = data.find(b"data")
        if i < 0 or j < 0:
            return 0.0
        import struct
        channels = struct.unpack("<H", data[i + 10:i + 12])[0] or 1
        rate = struct.unpack("<I", data[i + 12:i + 16])[0] or 16000
        bits = struct.unpack("<H", data[i + 22:i + 24])[0] or 16
        body = max(0, len(data) - j - 8)
        return body * 8.0 / (rate * channels * bits)
    except Exception:
        return 0.0


def transcribe_wav(path, context=""):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    messages = []
    ctx = str(context or "").strip()
    if ctx:
        messages.append({
            "role": "system",
            "content": "当前题目与术语参考，只用于提高识别准确率：\n" + ctx[:2500],
        })
    messages.append({"role": "user", "content": [
        {"audio": "data:audio/wav;base64," + b64}
    ]})
    body = {
        "model": ASR_MODEL,
        "input": {"messages": messages},
        "parameters": {"asr_options": {"enable_itn": True}},
    }
    data = _post(ASR_URL, body)
    usage_log.log("asr", ASR_MODEL, seconds=wav_seconds(path), usage=data.get("usage") or {})
    choices = (data.get("output") or {}).get("choices") or []
    if not choices:
        raise RuntimeError("ASR 没有返回结果")
    content = (choices[0].get("message") or {}).get("content") or []
    text = "".join(str(x.get("text") or "") for x in content if isinstance(x, dict)).strip()
    return {"text": text, "usage": data.get("usage", {})}


def default_chat_model():
    if chat_provider() == "deepseek":
        name = os.environ.get("TUTOR_DEEPSEEK_MODEL", "deepseek-flash")
        return name if name in CHAT_MODELS else "deepseek-flash"
    return CHAT_MODEL if CHAT_MODEL in CHAT_MODELS else "qwen-plus"


def model_available(name):
    info = CHAT_MODELS.get(name)
    if not info:
        return False
    return bool(deepseek_key()) if info["provider"] == "deepseek" else bool(get_key())


def chat_completion(messages, temperature=0.4, model=None):
    name = model or default_chat_model()
    info = CHAT_MODELS.get(name)
    if not info:
        raise RuntimeError("未知模型：%s" % name)
    if info["provider"] == "deepseek":
        key = deepseek_key()
        if not key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY")
        body = {"model": info["model"], "messages": messages, "temperature": temperature}
        data = _post(DEEPSEEK_URL, body, key=key, timeout=120)
    else:
        body = {"model": info["model"], "messages": messages, "temperature": temperature}
        data = _post(CHAT_URL, body, timeout=120)
    usage_log.log("llm", name, provider=info["provider"], usage=data.get("usage") or {})
    return data, info["provider"], name


def chat_reply(text, history=None, context="", model=None, mode="tutor", subject_id="math2", problem_type="single", background_only=False, extra="", history_window=8, temperature=0.4):
    if background_only:
        system = (
            "你是「讲伴」，一个陪学生讲题的学伴。学生正在把这道题讲给你听。"
            "学生没有明确卡住时，只回应他这一句：不展开讲解，不主动进入下一空/下一步，"
            "也不提前给下一步的关键提示；需要问时最多问一个，每次 1~3 句。"
            "不要为了问而问：学生已经说明白就接受；不要在学生答对后反问“确定吗”，"
            "也不要连续两轮追问同一个知识点。"
            "学生已经完整讲完、答案正确时，默认接受并停住，不要为了延续对话再找问题。"
            "学生举出具体例子后，先说明这个例子和题目说法是什么关系（反例/符合/无关），"
            "再问下一句；不要跳过这层，也不要问“这两个一样吗→那成立吗”这种没有必然联系的反问。"
            "只有学生的答案里有具体含糊、跳跃或前后矛盾时才验证；一次只验证一个点，验证过就过。"
            "验证题不要问一眼就有答案的机械步骤（比如“常数的导数是多少”）；"
            "要问能区分“真懂”和“背公式”的（比如“为什么这里会多出一个 a”），但只在确有含糊时才用。"
        )
    else:
        system = prompt_loader.compose(subject_id, problem_type, mode)
    if extra:
        system += "\n\n" + str(extra)
    if context:
        system += "\n\n当前题目背景：\n" + str(context)[:4000]
    messages = [{"role": "system", "content": system}]
    for item in (history or [])[-int(history_window or 8):]:
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": text})
    data, provider, name = chat_completion(messages, model=model, temperature=temperature)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("对话没有返回结果")
    raw = (choices[0].get("message") or {}).get("content", "")
    display, speech = split_reply(raw)
    return {"text": display, "speech": speech, "provider": provider, "model": name, "usage": data.get("usage", {})}


def normalize_transcript(text, model=None, context=""):
    """只整理本次新增的一句；context 只用于理解指代，不重复整理。"""
    name = model or NORMALIZE_MODEL
    if name not in CHAT_MODELS:
        name = "qwen-plus"
    prompt = (
        "你是数学语音转写的“公式化”编辑器。把学生口语中的数学表达式写成 LaTeX，其他中文原样保留。\n"
        "规则：\n"
        "1. 数学短语必须转成完整 LaTeX，公式里不要留“加/减/乘以/除以/比/趋于/的极限”这些中文。\n"
        "2. 例子：\n"
        "   “x ln e 加一除以 x 减一” → \\(x\\ln(e+\\frac{1}{x-1})\\)\n"
        "   “f(x) 比 x” → \\(\\frac{f(x)}{x}\\)\n"
        "   “ln(e 加一除以 x 减一) 的极限” → \\(\\ln(e+\\frac{1}{x-1})\\) 的极限\n"
        "3. 只整理“本次新增”的一段；不要重复、合并或改写前面的内容。\n"
        "4. 保留原句顺序和普通中文；不纠错、不补步骤、不解释。\n"
        "5. 不确定的词保留原词并加 [?]。\n"
        "6. 只输出整理后的本次内容，不要 Markdown、不要解释、不要前后缀。\n"
    )
    if context:
        prompt += "\n【前文，仅供理解指代，不要输出】\n" + str(context)[:3000] + "\n"
    prompt += "\n【本次新增】\n" + str(text)[:3000]
    data, provider, name = chat_completion([
        {"role": "user", "content": prompt}
    ], temperature=0.1, model=name)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("公式整理没有返回结果")
    return {
        "text": (choices[0].get("message") or {}).get("content", "").strip(),
        "provider": provider,
        "model": name,
        "usage": data.get("usage", {}),
    }


def summarize_problem(problem, history, model=None):
    """根据本轮对话生成整题收尾，返回结构化摘要。"""
    model = model or FINISH_MODEL
    text = str((problem or {}).get("text") or "")[:3000]
    reference = str((problem or {}).get("reference_answer") or "").strip()[:1200]
    opts = "\n".join(
        "%s. %s" % (o.get("label", ""), o.get("text", ""))
        for o in ((problem or {}).get("options") or []) if isinstance(o, dict)
    )[:2000]
    lines = []
    for item in (history or [])[-24:]:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            lines.append(("学生：" if role == "user" else "教练：") + content[:1200])
    prompt = (
        "你是数学教练，现在给一道刚讲完的题做“本题收尾”。\n"
        "只输出一个 JSON 对象，不要 Markdown 代码块，不要解释。字段：\n"
        "{\n"
        '  "outline": "思路骨架，3-5 步，公式可用 LaTeX",\n'
        '  "stuck": "学生卡住或纠正过的点，1-3 条",\n'
        '  "pitfalls": "本题易错点，1-3 条",\n'
        '  "suggested": "again|hard|good|easy",\n'
        '  "reason": "建议这个评级的一句话理由"\n'
        "}\n"
        "suggested 只能四选一：again=基本没掌握，hard=勉强，good=独立完成，easy=很熟。\n"
        "【本轮对话】只包含这一次复述；stuck 只看这一轮——这一轮讲得顺就留空，"
        "不要把以前轮次的卡点算进来。\n"
        "所有公式都用 \\( ... \\) 包起来，不要裸写 lim、frac、下标等 LaTeX。\n"
        "这是 JSON：字符串里的反斜杠必须双写——\\( 写成 \\\\(，\\frac 写成 \\\\frac，否则解析会失败。\n\n"
        "【题目】\n" + text + ("\n" + opts if opts else "") + "\n\n"
        + ("【隐藏参考结论，只用于校准，不要透露】\n" + reference + "\n\n" if reference else "")
        + "【本轮对话】\n" + "\n".join(lines)[:12000]
    )
    data, provider, name = chat_completion([
        {"role": "user", "content": prompt}
    ], temperature=0.2, model=model)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("收尾没有返回结果")
    raw = (choices[0].get("message") or {}).get("content", "").strip()
    obj = parse_model_json(raw)
    if not isinstance(obj, dict):
        # 补反斜杠也解析不了：别把原始 JSON 当“总结”展示给学生
        obj = {
            "outline": "" if raw.lstrip().startswith("{") else raw,
            "stuck": "", "pitfalls": "", "suggested": "good", "reason": "",
        }
    suggested = str(obj.get("suggested") or "good").lower()
    if suggested not in ("again", "hard", "good", "easy"):
        suggested = "good"
    return {
        "outline": str(obj.get("outline") or "").strip(),
        "stuck": str(obj.get("stuck") or "").strip(),
        "pitfalls": str(obj.get("pitfalls") or "").strip(),
        "suggested": suggested,
        "reason": str(obj.get("reason") or "").strip(),
        "reference": reference,
        "provider": provider,
        "model": name,
    }


def make_lesson_plan(problem, model=None):
    """为一道题写内部教案；只给教练用，不展示给学生。"""
    model = model or FINISH_MODEL
    text = str((problem or {}).get("text") or "")[:3000]
    opts = "\n".join(
        "%s. %s" % (o.get("label", ""), o.get("text", ""))
        for o in ((problem or {}).get("options") or []) if isinstance(o, dict)
    )[:2000]
    reference = str((problem or {}).get("reference_answer") or "").strip()[:1200]
    prompt = (
        "你是讲题教练的备课助手。为下面这道题写一份内部教案，学生看不到。\n"
        "只输出一个 JSON 对象，不要 Markdown，不要解释。字段：\n"
        "{\n"
        '  "goal": "这道题要讲透什么，一句话",\n'
        '  "prerequisites": ["先修概念/公式，1-3 条"],\n'
        '  "core": ["核心概念/方法，2-4 条"],\n'
        '  "path": ["解题路径骨架，3-5 步，不写完整演算"],\n'
        '  "misconceptions": [{"wrong":"常见错误理解","why":"为什么错","contrast":"正确对比"}],\n'
        '  "stuck": [{"point":"预期卡点","hint":"最小提示","next":"提示后让他做什么"}],\n'
        '  "hint_ladder": [{"level":1,"cue":"第一级线索"}],\n'
        '  "check_questions": ["收尾时要检查的问题，1-3 条"],\n'
        '  "success_criteria": ["学生做到什么算过关，1-3 条"],\n'
        '  "max_followups": 2,\n'
        '  "finish_check": ["学生收尾时必须说到的点，2-4 条"]\n'
        "}\n"
        "要求：\n"
        "- 教案只用于决定追问顺序，不把答案直接倒给学生；\n"
        "- 每个卡点只给最小提示，不给完整解法；\n"
        "- 同一卡点最多追问 max_followups 次，然后必须推进；\n"
        "- 公式用 \\( ... \\) 包起来。\n\n"
        "【题目】\n" + text + ("\n" + opts if opts else "") + "\n\n"
        + ("【隐藏参考结论，只用于备课，不要透露】\n" + reference + "\n" if reference else "")
    )
    data, provider, name = chat_completion([
        {"role": "user", "content": prompt}
    ], temperature=0.2, model=model)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("教案没有返回结果")
    raw = (choices[0].get("message") or {}).get("content", "").strip()
    obj = parse_model_json(raw)
    if not isinstance(obj, dict):
        raise RuntimeError("教案 JSON 解析失败")
    stuck = []
    for item in (obj.get("stuck") or [])[:4]:
        if isinstance(item, dict):
            stuck.append({
                "point": str(item.get("point") or "").strip(),
                "hint": str(item.get("hint") or "").strip(),
                "next": str(item.get("next") or "").strip(),
            })
    misconceptions = []
    for item in (obj.get("misconceptions") or [])[:3]:
        if isinstance(item, dict):
            misconceptions.append({
                "wrong": str(item.get("wrong") or "").strip(),
                "why": str(item.get("why") or "").strip(),
                "contrast": str(item.get("contrast") or "").strip(),
            })
    hint_ladder = []
    for item in (obj.get("hint_ladder") or [])[:3]:
        if isinstance(item, dict):
            hint_ladder.append({
                "level": int(item.get("level") or len(hint_ladder) + 1),
                "cue": str(item.get("cue") or "").strip(),
            })
    return {
        "goal": str(obj.get("goal") or "").strip(),
        "prerequisites": [str(x).strip() for x in (obj.get("prerequisites") or []) if str(x).strip()][:3],
        "core": [str(x).strip() for x in (obj.get("core") or []) if str(x).strip()][:4],
        "path": [str(x).strip() for x in (obj.get("path") or []) if str(x).strip()][:5],
        "misconceptions": misconceptions,
        "stuck": stuck,
        "hint_ladder": hint_ladder,
        "check_questions": [str(x).strip() for x in (obj.get("check_questions") or []) if str(x).strip()][:3],
        "success_criteria": [str(x).strip() for x in (obj.get("success_criteria") or []) if str(x).strip()][:3],
        "max_followups": 2,
        "finish_check": [str(x).strip() for x in (obj.get("finish_check") or []) if str(x).strip()][:4],
        "provider": provider,
        "model": name,
    }


def merge_finish_check(rubric, plan):
    """把教案的收尾检查点并入内部 rubric，不覆盖已有字段。"""
    if not isinstance(rubric, dict) or not isinstance(plan, dict):
        return rubric
    checks = [str(x).strip() for x in (plan.get("finish_check") or []) if str(x).strip()]
    questions = [str(x).strip() for x in (plan.get("check_questions") or []) if str(x).strip()]
    if checks:
        rubric["finish_check"] = checks
    if questions:
        rubric["check_questions"] = questions
    return rubric


def compare_with_plan(plan, answer, model=None):
    """只把学生回答和教案逐项对比；不纠正、不解释、不追问。"""
    if not isinstance(plan, dict) or not plan:
        raise RuntimeError("还没有教案")
    answer = str(answer or "").strip()
    if not answer:
        raise RuntimeError("回答为空")
    model = model or FINISH_MODEL
    plan_view = {
        "goal": plan.get("goal") or "",
        "core": plan.get("core") or [],
        "misconceptions": plan.get("misconceptions") or [],
        "finish_check": plan.get("finish_check") or [],
        "success_criteria": plan.get("success_criteria") or [],
    }
    prompt = (
        "你是对比器，不是老师，也不是评分器。只把学生回答和教案对照，输出事实。\n"
        "严格禁止：纠正、解释、给建议、提问、补知识、评价对错程度。\n"
        "先判断学生是否已经用等价说法覆盖了教案点；不要机械看字面。\n"
        "等价规则：\n"
        "- “每个子树 / 每个结点都满足” ≡ “不能只看根”“任一结点失衡就淘汰”；\n"
        "- “|BF|≤1 是判据” ≡ “|BF|>1 即淘汰该选项”；\n"
        "- “逐点算高度差” ≡ “逐层/逐子树检查”；\n"
        "- 学生分析当前选项、代入选项、写具体树，属于解题过程，不算教案外内容；\n"
        "- 同一个意思只出现一次，不要在 hit 和 miss 同时出现。\n"
        "miss 只列真正没覆盖的核心知识，最多 4 条；能从学生话里直接推出就算覆盖。\n"
        "confused 只列学生明确说错/用错的点；不列“学生曾疑惑”“不理解报告”这类元评论。\n"
        "extra 只列跑题知识；不列当前选项的推理。\n"
        "措辞像人：用“你已经说到”“还差”这种短句，不用“未提……”的机械否定。\n"
        "只输出 JSON，不要 Markdown，不要额外文字：\n"
        '{"hit":["学生已经表达到的点"],'
        '"miss":["还差的核心点"],'
        '"confused":["学生明确说错/用错的点"],'
        '"extra":["跑题内容，只记录"]}\n\n'
        "【教案】\n" + json.dumps(plan_view, ensure_ascii=False)[:5000] +
        "\n\n【学生回答】\n" + answer[:4000]
    )
    data, provider, name = chat_completion([
        {"role": "user", "content": prompt}
    ], temperature=0.1, model=model)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("对比没有返回结果")
    raw = (choices[0].get("message") or {}).get("content", "").strip()
    obj = parse_model_json(raw)
    if not isinstance(obj, dict):
        raise RuntimeError("对比 JSON 解析失败")
    limits = {"hit": 6, "miss": 4, "confused": 2, "extra": 2}
    def arr(key):
        out = []
        for x in (obj.get(key) or []):
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
        return out[:limits.get(key, 4)]
    return {
        "hit": arr("hit"),
        "miss": arr("miss"),
        "confused": arr("confused"),
        "extra": arr("extra"),
        "provider": provider,
        "model": name,
    }


def evaluate_summary(rubric, summary, model=None):
    """对照内部 rubric 检查学生总结，只返回一个启发式问题或 done；不暴露 rubric。"""
    model = model or FINISH_MODEL
    summary = str(summary or "").strip()
    if len(summary) < 8:
        return {"done": False, "question": "先用一句话说：这题最关键的一步是什么？"}
    checks = rubric.get("finish_check") if isinstance(rubric, dict) else []
    questions = rubric.get("check_questions") if isinstance(rubric, dict) else []
    check_note = ""
    if checks:
        check_note += "\n【教案要求覆盖的收尾点】\n" + "\n".join("- " + str(x) for x in checks[:6])
    if questions:
        check_note += "\n【可用的检查问题】\n" + "\n".join("- " + str(x) for x in questions[:4])
    prompt = (
        "你是数学题的收尾教练。下面有一份“内部参考答案”和“学生自己的总结”。\n"
        "内部参考答案只是用来检查，不要展示、不要复述、不要透露。\n"
        "检查学生的总结是否覆盖：关键步骤、关键依据、结果、主要易错点。\n"
        "如果给了教案收尾点，也要检查这些点是否被覆盖。\n"
        "允许学生用不同解法；只要逻辑成立，不要因为和参考答案不同就判错。\n"
        "只输出 JSON：{\"done\": true/false, \"question\": \"...\"}\n"
        "如果 done=false，只问一个最关键的问题；问题要启发式，不能包含答案，不能列清单，不超过 60 字。\n"
        "如果 done=true，question 留空。\n" + check_note + "\n\n"
        "【内部参考答案】\n" + json.dumps(rubric, ensure_ascii=False)[:5000] +
        "\n\n【学生总结】\n" + summary[:3000]
    )
    data, provider, name = chat_completion([
        {"role": "user", "content": prompt}
    ], temperature=0.1, model=model)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("收尾比较没有返回结果")
    raw = (choices[0].get("message") or {}).get("content", "").strip()
    obj = parse_model_json(raw)
    if not isinstance(obj, dict):
        return {"done": False, "question": "你刚才的总结里，最关键的一步依据是什么？"}
    done = bool(obj.get("done"))
    question = str(obj.get("question") or "").strip()
    if not done and not question:
        question = "你刚才的总结里，最关键的一步依据是什么？"
    return {"done": done, "question": "" if done else question[:200]}


def _feedback_numbers(text):
    return re.findall(r"20\d{2}|\d+(?:\.\d+)?%", str(text or ""))


def _feedback_claims_missing(text):
    return bool(re.search(r"缺|未提|没提|没有提|忽略|遗漏|补入|补上|加入|加进", str(text or "")))


def _clean_feedback_claims(issues, next_action, draft):
    """防止模型把草稿里已经写过的数据说成缺失。"""
    kept = []
    for item in issues:
        problem = str(item.get("problem") or "")
        nums = _feedback_numbers(problem)
        if _feedback_claims_missing(problem) and nums and all(n in draft for n in nums):
            continue
        kept.append(item)
    nums = _feedback_numbers(next_action)
    if _feedback_claims_missing(next_action) and nums and all(n in draft for n in nums):
        next_action = kept[0].get("action") if kept else "这次只改一处：把已有数据用得更准。"
    return kept, next_action


def review_writing(prompt, draft, part="B", model=None, chart_data=None):
    """英二写作批改：只给评分点、问题和下一步，不代写全文。"""
    model = model or FINISH_MODEL
    prompt = str(prompt or "")[:4000]
    draft = str(draft or "").strip()
    part = "A" if str(part).upper().startswith("A") else "B"
    words = len(re.findall(r"[A-Za-z]+(?:['-][A-Za-z]+)?", draft))
    if not draft:
        raise RuntimeError("草稿为空")
    total = 10 if part == "A" else 15
    kind = "小作文（书信/邮件）" if part == "A" else "大作文（图表作文）"
    rubric = (
        "小作文评分点：任务完成（是否覆盖题目要求）、格式与语气（书信/邮件）、语言准确与连贯、字数。"
        if part == "A" else
        "大作文评分点：图表信息解读、论点与展开、结构连贯、语言准确与多样、字数。"
    )
    if part == "A":
        part_guide = (
            "【小作文专项】\n"
            "- 先看称呼、落款、身份和语气是否符合书信/邮件；\n"
            "- task 看题目每条 bullet 是否都回应，不能只写一个；\n"
            "- structure 看开头说明目的、主体给建议/说明、结尾礼貌收束；\n"
            "- 不要把建议写成大作文式议论；\n"
            "- 如果题目要求 Li Ming/Zhang Wei，检查是否用错名字。"
        )
    else:
        part_guide = (
            "【大作文专项】\n"
            "- 先看是否引用图表关键数据/趋势，不能只写空泛观点；\n"
            "- 结构应是：描述图表 → 解释原因 → 评论/建议；\n"
            "- 至少检查两个具体数据点是否被使用；\n"
            "- 检查是否只描述不解释，或解释与图表无关；\n"
            "- 不要把图表作文写成书信。"
        )
    chart_section = ""
    if chart_data:
        chart_section = "\n【图表数据（以此为准）】\n" + json.dumps(chart_data, ensure_ascii=False, indent=2) + "\n"
    instruction = (
        "你是考研英语二写作教练。请按评分点批改学生草稿，但不要代写、不要给完整范文。\n"
        "现阶段只抓硬伤，不追高级表达。must_fix 只允许以下五类：\n"
        "A. 图表数据看错；B. 题目要求没覆盖；C. 段落之间逻辑断了；D. 句子读不懂；E. 明显语法错误影响意思。\n"
        "规则：\n"
        "0. 先数字数：Part A 少于 70 词、Part B 少于 105 词时，直接记一条 B 类任务未完成；字数问题只记一条，不重复。\n"
        "1. 同义词、句式漂亮、语气更地道、老师个人偏好，一律放 optional，不得放 must_fix；\n"
        "2. must_fix 0-1 条；没有硬伤就空数组，rewrite_required=false；不要为了显得认真硬找问题；\n"
        "3. 每条 must_fix 必须逐字引用学生原句（quote 原样摘录，不要改写）；\n"
        "4. problem 说明硬伤，fix 只给修改方向，不给完整替换段落；\n"
        "5. optional 0-2 条，只写可选润色；没有就不写；\n"
        "6. 允许学生用不同表达；不要因为和模板/范文不同就判错；\n"
        "7. 提“缺数据/缺某句”前先全文核对；草稿里已经出现的数字、要求、人名，不得判为缺失；\n"
        "8. 英二档位参考：第五档 A 9-10/B 13-15；第四档 A 7-8/B 10-12；第三档 A 5-6/B 7-9；第二档 A 3-4/B 4-6；第一档 A 1-2/B 1-3。先判任务完成，再看语言；分数只作参考。\n"
        "9. 图表类别允许同义改写；只有数字错或类别明显错位（如把 33%% 写成 37%%）才算 A 类数据错误。不要把 other 的泛指、重复表达判成数据错误。\n"
        "10. 句子简单、词汇基础、表达重复、衔接朴素，只放 optional；只有读不懂、逻辑断、任务漏才进 must_fix。\n"
        "11. 字数低于目标 70%% 时，只算一条 B 类任务未完成（A 少于 70 词，B 少于 105 词），不要重复列多条字数问题。\n"
        "12. 如果提供了【图表数据】，以它为准：数字或类别与它明显冲突才算 A 类；没有提供时才按上一条，不要靠残缺题干猜。\n"
        "13. 如果 chart_data 标了 approximate=true，学生用 about/around/约 的读数不算数据错；只有类别或数量级明显错才判。判“缺单位/缺数字”前先看 quote 里是否已经写了单位和数字。\n"
        "14. 同一个根因只报一条；缺一个任务点只报一条，不要拆成“逻辑断”和“任务没覆盖”两条；无关信息不要单独占第二条。\n"
        "15. 分数只作参考，不追求精确；没有硬伤时不要用低分制造焦虑；\n"
        "16. 只输出 JSON，不要 Markdown 代码块，不要解释。\n\n"
        "JSON 格式：\n"
        "{\n"
        '  "must_fix": [{"quote": "学生原句", "problem": "硬伤", "fix": "修改方向"}],\n'
        '  "optional": ["可选润色，不影响定稿"],\n'
        '  "rewrite_required": false,\n'
        '  "scores": {"task": 0, "structure": 0, "language": 0}\n'
        "}\n"
        "must_fix 0-2 条；optional 0-2 条；rewrite_required 必须与 must_fix 是否为空一致；scores 为 0-%d。\n\n"
        "%s\n"
        "【题型】%s\n【评分点】%s\n【题目】\n%s\n%s\n【学生草稿】\n%s\n"
        "【词数】约 %d 词；目标：%s"
    ) % (
        total, part_guide, kind, rubric, prompt, chart_section, draft[:8000], words,
        "约 100 词" if part == "A" else "约 150 词",
    )
    data, provider, name = chat_completion(
        [{"role": "user", "content": instruction}], temperature=0.2, model=model
    )
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("写作批改没有返回结果")
    raw = (choices[0].get("message") or {}).get("content", "").strip()
    obj = parse_model_json(raw)
    if not isinstance(obj, dict):
        raise RuntimeError("写作批改 JSON 解析失败")
    scores = obj.get("scores") if isinstance(obj.get("scores"), dict) else {}
    clean_scores = {}
    for key in ("task", "structure", "language"):
        try:
            clean_scores[key] = max(0, min(total, int(scores.get(key, 0))))
        except (TypeError, ValueError):
            clean_scores[key] = 0
    must_raw = obj.get("must_fix")
    if not isinstance(must_raw, list):
        must_raw = obj.get("issues") if isinstance(obj.get("issues"), list) else []
    must_fix = []
    draft_norm = re.sub(r"\s+", " ", draft).strip().lower()
    for item in must_raw[:2]:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "").strip()[:300]
        quote_norm = re.sub(r"\s+", " ", quote).strip().lower()
        if not quote_norm or quote_norm not in draft_norm:
            continue
        must_fix.append({
            "quote": quote,
            "problem": str(item.get("problem") or "").strip()[:300],
            "action": str(item.get("fix") or item.get("action") or "").strip()[:300],
        })
    optional = []
    for x in (obj.get("optional") or [])[:2]:
        s = str(x or "").strip()[:300]
        if s:
            optional.append(s)
    next_action = str(obj.get("next_action") or "").strip()[:300]
    must_fix, next_action = _clean_feedback_claims(must_fix, next_action, draft)
    def _issue_rank(item):
        text = str(item.get("problem") or "").strip().upper()
        for i, letter in enumerate(("A", "B", "C", "D", "E")):
            if text.startswith(letter):
                return i
        if any(k in text for k in ("图表数据", "数据看错", "数据错", "百分比", "数字错", "数字不")):
            return 0
        if any(k in text for k in ("没覆盖", "没有覆盖", "缺少", "遗漏", "未完成", "不符合要求", "任务未", "要求没", "字数不足")):
            return 1
        if any(k in text for k in ("逻辑断", "逻辑混乱", "不连贯", "段落之间没有", "衔接不", "缺少过渡", "跳跃")):
            return 2
        if any(k in text for k in ("读不懂", "句子不", "句子错", "句子混乱")):
            return 3
        if any(k in text for k in ("语法错", "语法错误", "主谓不一致", "时态错", "拼写错", "用词错")):
            return 4
        return 9
    must_fix = sorted(must_fix, key=_issue_rank)[:1]
    min_words = 70 if part == "A" else 105
    if words < min_words and not any("字数" in (x.get("problem") or "") for x in must_fix):
        target_words = 100 if part == "A" else 150
        length_action = writing_expansion.format_advice(
            writing_expansion.expansion_advice(part, draft, target_words, chart_data),
            target_words,
        )
        must_fix = [{
            "quote": draft[:160],
            "problem": "字数明显不足：当前约 %d 词，低于目标 %s 的 70%%。" % (words, "100 词" if part == "A" else "150 词"),
            "action": length_action,
        }] + must_fix[:1]
    rewrite_required = bool(must_fix)
    if rewrite_required:
        if must_fix and str(must_fix[0].get("problem") or "").startswith("字数"):
            next_action = "这次只改：" + must_fix[0]["action"]
        next_action = next_action or ("这次只改：" + (must_fix[0].get("action") or must_fix[0].get("problem") or ""))
        if not next_action.startswith("这次只改"):
            next_action = "这次只改：" + next_action
    else:
        next_action = ""
    return {
        "scores": clean_scores,
        "must_fix": must_fix,
        "optional": optional,
        "rewrite_required": rewrite_required,
        "issues": must_fix,
        "next_action": next_action,
        "words": words,
        "total": total,
        "provider": provider,
        "model": name,
    }


def synth_wav(text, out_dir, provider=None, voice=None):
    text = spoken_text(text)
    if not text:
        raise RuntimeError("TTS 文本为空")
    if len(text) > 600:
        text = text[:600]
    provider = (provider or TTS_PROVIDER or "local").strip().lower()
    voice = (voice or TTS_VOICE).strip()
    if provider == "local":
        try:
            local_tts.ensure(wait=60)
            req = urllib.request.Request(
                TTS_LOCAL_URL + "/tts",
                data=json.dumps({"text": text}, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read().decode("utf-8"))
            name = str(data.get("file") or "")
            path = os.path.join(out_dir, name)
            if name and os.path.isfile(path):
                usage_log.log("tts-local", "qwen3-tts-0.6b", chars=len(text))
                return {"file": name, "usage": {"provider": "local-qwen3", "elapsed": data.get("elapsed")}}
        except Exception:
            pass
    body = {"model": TTS_MODEL, "input": {"text": text, "voice": voice, "language_type": "Chinese"}}
    data = _post(TTS_URL, body)
    usage_log.log("tts", TTS_MODEL, chars=len(text), usage=data.get("usage") or {})
    audio = (data.get("output") or {}).get("audio") or {}
    url = audio.get("url")
    if not url:
        raise RuntimeError("TTS 没有返回音频 URL")
    os.makedirs(out_dir, exist_ok=True)
    name = uuid.uuid4().hex + ".wav"
    path = os.path.join(out_dir, name)
    try:
        with urllib.request.urlopen(url, timeout=120) as r, open(path, "wb") as f:
            f.write(r.read())
    except Exception as e:
        raise RuntimeError("下载 TTS 音频失败：%s" % e)
    # 清掉 7 天前的合成音频，避免越积越多
    cutoff = time.time() - 7 * 86400
    try:
        for n in os.listdir(out_dir):
            p = os.path.join(out_dir, n)
            if n.endswith(".wav") and os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                try:
                    os.remove(p)
                except BaseException:
                    pass
    except BaseException:
        pass
    return {"file": name, "usage": data.get("usage", {})}
