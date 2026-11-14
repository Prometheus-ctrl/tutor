#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tutor 校正页服务：端口 8793，独立于稳定版 8080/8791。

GET  /api/papers                 列出 samples/ingest-* 的卷子
GET  /api/paper/<id>             读取 result.json + 图片 URL
POST /api/paper/<id>/save        保存修正后的 problems（原文/bbox/选项），并重裁
GET  /media/<id>/<path>          题图/页图
GET  /                           校正页
"""
import json
import html
import mimetypes
import base64
import datetime
import os
import random
import re
import sys
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, "samples")
WEB = os.path.join(ROOT, "web")
PORT = int(os.environ.get("TUTOR_PORT", "8793"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app_api  # noqa: E402
import db as appdb  # noqa: E402
import ingest  # noqa: E402
import learning_report  # noqa: E402
import local_tts  # noqa: E402
import review_store  # noqa: E402
import session_store  # noqa: E402
import preference_store  # noqa: E402
import feedback_store  # noqa: E402
import companion_config  # noqa: E402
import speech  # noqa: E402
import tutor_policy  # noqa: E402
import tutor_router  # noqa: E402
import tutor_scenarios  # noqa: E402
import tutor_validator  # noqa: E402
import usage_log  # noqa: E402
import vision  # noqa: E402

DATA = os.path.join(ROOT, "data")
FIGURE_CACHE = os.path.join(DATA, "figure_desc.json")
FINISH_SESSIONS = {}
FINISH_TTL = 30 * 60
DISTRESS = ("进行不下去", "一直追问", "循环", "别问", "不知道", "不会", "给提示", "卡住", "跳过")


def _figure_cache():
    try:
        with open(FIGURE_CACHE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _figure_description(paper, index):
    if not paper or index is None:
        return ""
    try:
        p = app_api.problem_at(str(paper), int(index))
        if not p:
            return ""
        saved = app_api.get_problem_figure(p.get("id") or "")
        if saved and saved.get("description"):
            return saved["description"]
        text = str(p.get("text") or "")
        if not re.search(r"[图表]|如图|如右|所示图", text):
            return ""
        pid = str(p.get("id") or "")
        cache_key = pid + ":page2"
        cache = _figure_cache()
        if cache_key in cache:
            return cache[cache_key]
        d = paper_dir(str(paper))
        if not d:
            return ""
        page = int(p.get("page") or 1)
        page_path = os.path.join(d, "pages", "page-%02d.jpg" % page)
        crop = str(p.get("crop") or "")
        crop_path = os.path.join(d, crop) if crop else ""
        path = page_path if os.path.isfile(page_path) else crop_path
        if not path or not os.path.isfile(path):
            return ""
        focus = "第%s题：%s" % (p.get("no") or (int(index) + 1), text[:300])
        desc = vision.describe_figure(path, focus=focus)
        if desc:
            cache[cache_key] = desc
            os.makedirs(DATA, exist_ok=True)
            with open(FIGURE_CACHE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        return desc
    except Exception:
        return ""


def _gap_answer(history, text):
    chunks = []
    for m in history or []:
        if (m or {}).get("role") == "user":
            c = str((m or {}).get("content") or "").strip()
            if c:
                chunks.append(c)
    chunks = chunks[-3:]
    t = str(text or "").strip()
    if t and not any(k in t for k in ("讲完了", "检查", "看看", "复盘")):
        chunks.append(t)
    return "\n".join(chunks)


def _format_gap_check(c):
    labels = (("hit", "你讲到的点"), ("miss", "还差的点"), ("confused", "说错/用错"), ("extra", "题外内容"))
    lines = []
    for key, label in labels:
        arr = c.get(key) or []
        if not arr:
            continue
        lines.append(label + "：")
        lines.extend("- " + str(x) for x in arr)
        lines.append("")
    return "\n".join(lines).strip() or "这次没有可对照的内容。"


def _role_fallback(role, plan, text, state):
    if role in ("gap_fill", "guide"):
        return _force_hint(plan, text, int((state or {}).get("hint_level", 0)))
    if role == "summary":
        return "你的总结已记录。先按你自己的说法保留，不再补充。"
    return "先按你自己的节奏继续。"


def _question_streak(history):
    n = 0
    for m in reversed(history or []):
        role = (m or {}).get("role")
        content = str((m or {}).get("content") or "")
        if role == "user":
            continue
        if role == "assistant" and re.search(r"[？?]", content):
            n += 1
            continue
        break
    return n


def _should_force(text, state=None, move=None):
    """只在明确卡住或追问超预算时强制提示，正常分析不截断。"""
    if any(k in str(text or "") for k in DISTRESS):
        return True
    if (state or {}).get("over_budget") and move == "answer":
        return True
    return False


def _force_hint(plan, text, level=0):
    """连续追问或学生明确卡住时，按提示阶梯给最小提示。"""
    plan = plan or {}
    if int(level or 0) >= 3:
        return "先停一下：这道题已经给过三级提示，再追问下去只会更卡。你可以选：看一小段解析、先换一道、或者休息两分钟再回来。"
    ladder = [x for x in (plan.get("hint_ladder") or []) if isinstance(x, dict)]
    ladder.sort(key=lambda x: int(x.get("level") or 0))
    cue = ""
    if ladder:
        idx = min(max(int(level or 0), 0), len(ladder) - 1)
        cue = str(ladder[idx].get("cue") or "").strip()
    nxt = ""
    for s in plan.get("stuck") or []:
        if not cue:
            cue = str(s.get("hint") or "").strip()
        if not nxt:
            nxt = str(s.get("next") or "").strip()
        if cue and nxt:
            break
    if cue:
        body = "先停一下，不再重复追问。提示：" + cue
        if nxt:
            body += " 下一步：" + nxt
        return body
    return "先停一下，不再重复追问。只做一步：用一句话说出题目里的操作顺序，然后我接着帮你。"

mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("font/ttf", ".ttf")

SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def paper_dir(pid):
    if not SAFE_ID.match(pid or ""):
        return None
    path = os.path.join(SAMPLES, pid)
    if not os.path.isdir(path) or not os.path.isfile(os.path.join(path, "result.json")):
        return None
    return path


def slice_batch_history(hist):
    """客户端传来的历史里，只保留最后一轮（从最后一个 batchStart 起）。"""
    hist = list(hist or [])
    last = 0
    for i, m in enumerate(hist):
        if m.get("batchStart"):
            last = i
    return hist[last:]


def current_round_history(pid, index, fallback=None):
    """收尾只看当前这一轮：优先取开着的会话；否则按批次切客户端传来的历史。

    旧逻辑把这道题所有轮次（含第一轮）都喂给收尾模型，导致第一轮的卡点被
    当成这一轮的卡点。这里只保留本轮 user/assistant。
    """
    try:
        data = session_store.history_for_problem(pid, index)
        sid = data.get("sessionId")
        if sid:
            for batch in data.get("batches") or []:
                if batch.get("id") != sid:
                    continue
                turns = [
                    {"role": t.get("role"), "content": t.get("content")}
                    for t in (batch.get("turns") or [])
                    if t.get("role") in ("user", "assistant") and str(t.get("content") or "").strip()
                ]
                if turns:
                    return turns
    except Exception:
        pass
    return slice_batch_history(fallback)


_RATING_CN = {"again": "重来", "hard": "困难", "good": "良好", "easy": "简单"}


def _summary_detail(text, max_chars=200):
    """从学伴总结里只取卡点/易错，丢掉思路骨架（避免复述被剧透）。"""
    parts = []
    for line in str(text or "").split("\n"):
        line = line.strip()
        if line.startswith("卡点：") or line.startswith("易错："):
            parts.append(line)
    body = "；".join(parts) if parts else str(text or "").strip().replace("\n", " ")
    return body[:max_chars]


def round_memory_block(paper, index, mode="tutor", max_rounds=2, max_chars=200):
    """把之前几轮复述的总结压成一小段，作为跨轮记忆拼进上下文。"""
    paper = str(paper or "")
    if not paper:
        return ""
    try:
        hist = session_store.history_for_problem(paper, int(index))
    except Exception:
        return ""
    batches = hist.get("batches") or []
    current = hist.get("sessionId")
    ended = [b for b in batches if b.get("id") != current and (b.get("turns") or [])]
    if not ended:
        return ""
    ratings = {}
    try:
        for ev in review_store.ratings_for_problem(paper, int(index)):
            sid = str(ev.get("session_id") or "")
            if sid:
                ratings[sid] = ev.get("rating")
    except Exception:
        pass
    fallback_summary = ""
    try:
        item = review_store.get("%s:%d" % (paper, int(index)))
        if item and isinstance(item.get("summary"), dict):
            fallback_summary = str(item["summary"].get("user") or "")
    except Exception:
        pass
    ids = [b.get("id") for b in batches]
    selected = ended[-max_rounds:]
    lines = []
    for b in selected:
        no = (ids.index(b.get("id")) + 1) if b.get("id") in ids else 0
        ts = b.get("ended_at") or b.get("created_at") or 0
        when = time.strftime("%m-%d", time.localtime(int(ts))) if ts else ""
        rating = ratings.get(str(b.get("id")))
        label = "第 %d 次%s%s" % (
            no,
            ("（" + when + "）") if when else "",
            ("，评级 " + _RATING_CN.get(rating, rating)) if rating else "",
        )
        summary = ""
        for t in b.get("turns") or []:
            if t.get("role") == "summary" and str(t.get("content") or "").strip():
                summary = str(t["content"])
        if not summary and b is selected[-1] and fallback_summary:
            summary = fallback_summary
        if mode == "review":
            lines.append(label + "：之前已经讲过一遍。")
        else:
            lines.append(label + "：" + (_summary_detail(summary, max_chars) if summary else "之前已经讲过一遍。"))
    if not lines:
        return ""
    out = ["【这题之前复述过的轮次（历史记录，只作参考：不要主动提起，也不要当成这一轮的内容）】"]
    out.extend(lines)
    if mode == "review":
        out.append("【复述模式：不要据此提示、纠正或评判本轮，只当这题练过几次】")
    else:
        out.append("【不要主动说“上次你卡在……”，除非学生自己问起】")
    return "\n".join(out)


def wav_peak(path):
    """返回 WAV 录音的峰值（0~1），用来识别“没听到声音”的录音。

    静音录音交给 ASR 时，模型容易把上下文（题目原文）当成听写结果返回。
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
        if data[:4] != b"RIFF":
            return 0.0
        idx = data.find(b"data")
        if idx < 0:
            return 0.0
        body = data[idx + 8:]
        body = body[:len(body) - (len(body) % 2)]
        if not body:
            return 0.0
        import array
        samples = array.array("h")
        samples.frombytes(body)
        if not samples:
            return 0.0
        return max(max(samples), -min(samples)) / 32768.0
    except Exception:
        return 0.0


def safe_remove(path):
    """删除文件：任何 BaseException 都不能中断正在处理的请求。

    Windows 上外部文件守卫/杀软可能用 SystemExit 之类中断删除，
    ASR 轮转清理时如果它冒出来，整个请求会直接断连（浏览器报 Failed to fetch）。
    """
    try:
        os.remove(path)
        return True
    except BaseException:
        return False


def keep_asr_audio(data, keep=10):
    """把最近几条录音留在本地（tutor/data/asr-debug），方便排查识别问题。"""
    try:
        d = os.path.join(DATA, "asr-debug")
        os.makedirs(d, exist_ok=True)
        name = time.strftime("%Y%m%d-%H%M%S") + "-%03d.wav" % (time.time_ns() % 1000)
        with open(os.path.join(d, name), "wb") as f:
            f.write(data)
        files = sorted(f for f in os.listdir(d) if f.endswith(".wav"))
        for old in files[:-keep]:
            safe_remove(os.path.join(d, old))
    except BaseException:
        pass


# ---- API 用量与花费估算 ----
# 价格单位：llm 为 元/百万 token（命中/未命中/输出，[空闲, 高峰]）；asr 为 元/秒。
# 均为公开价估算，可能变动，实际以服务商账单为准。
PRICES = {
    "deepseek-flash": {"hit": (0.02, 0.04), "miss": (1.0, 2.0), "out": (4.0, 8.0)},
    "deepseek-v4-pro": {"hit": (0.15, 0.30), "miss": (4.5, 9.0), "out": (13.5, 27.0)},
    "qwen-plus": {"hit": (0.8, 0.8), "miss": (0.8, 0.8), "out": (2.0, 2.0)},
    "qwen-max": {"hit": (2.4, 2.4), "miss": (2.4, 2.4), "out": (9.6, 9.6)},
    "qwen3-vl-plus": {"hit": (3.0, 3.0), "miss": (3.0, 3.0), "out": (3.0, 3.0)},
}
ASR_PRICE_PER_SEC = 0.00022
TTS_PRICE_PER_KCHAR = 0.0


def _peak_time(ts):
    try:
        dt = datetime.datetime.fromtimestamp(ts)
    except Exception:
        return False
    return dt.weekday() < 5 and ((9 <= dt.hour < 12) or (14 <= dt.hour < 18))


def usage_cost(rec):
    kind = rec.get("kind") or ""
    if kind == "asr":
        return float(rec.get("seconds") or 0) * ASR_PRICE_PER_SEC
    if kind == "tts":
        return float(rec.get("chars") or 0) / 1000.0 * TTS_PRICE_PER_KCHAR
    if kind == "tts-local":
        return 0.0
    price = PRICES.get(rec.get("model") or "")
    if not price:
        return 0.0
    i = 1 if _peak_time(rec.get("ts") or 0) else 0
    usage = rec.get("usage") or {}
    tin = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    tout = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    hit = usage.get("prompt_cache_hit_tokens")
    miss = usage.get("prompt_cache_miss_tokens")
    if hit is None and miss is None:
        hit, miss = 0, tin
    return (hit * price["hit"][i] + miss * price["miss"][i] + tout * price["out"][i]) / 1000000.0


def usage_summary(days=7):
    now = time.time()
    days = max(1, min(31, int(days or 7)))
    start = now - days * 86400
    today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    items = {}
    daily = {}
    total = 0.0
    today_cost = 0.0
    calls = 0
    try:
        with open(usage_log.PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                ts = rec.get("ts") or 0
                if ts < start:
                    continue
                cost = usage_cost(rec)
                calls += 1
                total += cost
                day = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                daily[day] = daily.get(day, 0.0) + cost
                if ts >= today_start:
                    today_cost += cost
                    key = (rec.get("kind") or "", rec.get("model") or "")
                    it = items.setdefault(key, {
                        "kind": key[0], "model": key[1], "calls": 0, "seconds": 0.0,
                        "chars": 0, "tokensIn": 0, "tokensOut": 0, "cost": 0.0,
                    })
                    it["calls"] += 1
                    it["seconds"] += float(rec.get("seconds") or 0)
                    it["chars"] += int(rec.get("chars") or 0)
                    u = rec.get("usage") or {}
                    it["tokensIn"] += int(u.get("prompt_tokens") or u.get("input_tokens") or 0)
                    it["tokensOut"] += int(u.get("completion_tokens") or u.get("output_tokens") or 0)
                    it["cost"] += cost
    except OSError:
        pass
    rows = sorted(items.values(), key=lambda x: -x["cost"])
    for it in rows:
        it["cost"] = round(it["cost"], 4)
        it["seconds"] = round(it["seconds"], 1)
    day_rows = [{"date": d, "cost": round(c, 4)} for d, c in sorted(daily.items())]
    return {
        "days": days,
        "today": {"date": datetime.datetime.now().strftime("%Y-%m-%d"), "cost": round(today_cost, 4), "items": rows},
        "range": {"cost": round(total, 4), "calls": calls, "daily": day_rows},
        "note": "估算：ASR 按 0.00022 元/秒（前 10 小时免费）；DeepSeek 按官方价、空闲时段半价；qwen 系列与 TTS 为粗估；实际以服务商账单为准。",
    }


def list_papers():
    out = []
    if not os.path.isdir(SAMPLES):
        return out
    meta = {}
    try:
        c = appdb.connect()
        meta = {r["id"]: {"title": r["title"], "subject_id": r["subject_id"]}
                for r in c.execute("SELECT id,title,subject_id FROM papers").fetchall()}
        c.close()
    except Exception:
        meta = {}
    for name in sorted(os.listdir(SAMPLES), reverse=True):
        d = paper_dir(name)
        if not d:
            continue
        try:
            with open(os.path.join(d, "result.json"), encoding="utf-8") as f:
                r = json.load(f)
            m = meta.get(name) or {}
            out.append({"id": name, "title": m.get("title") or name,
                        "subject_id": m.get("subject_id") or "math2",
                        "pages": r.get("pages", 0), "problems": len(r.get("problems") or []),
                        "mtime": os.path.getmtime(os.path.join(d, "result.json"))})
        except (OSError, ValueError):
            continue
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "TutorReview/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _file(self, path):
        if not os.path.isfile(path):
            self._json(404, {"error": "not found"})
            return
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        data = open(path, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            pass

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/usage/summary":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                days = int((q.get("days") or ["7"])[0])
            except (TypeError, ValueError):
                days = 7
            return self._json(200, usage_summary(days))
        if path == "/api/health":
            provider = speech.chat_provider()
            default = speech.default_chat_model()
            return self._json(200, {
                "ok": True,
                "chatProvider": provider,
                "chatModel": default,
                "models": [
                    {
                        "id": k,
                        "label": v["label"],
                        "provider": v["provider"],
                        "available": speech.model_available(k),
                    }
                    for k, v in speech.CHAT_MODELS.items()
                ],
                "asrModel": speech.ASR_MODEL,
                "ttsModel": speech.TTS_MODEL,
                "visionModel": vision.MODEL,
            })
        if path == "/api/papers":
            return self._json(200, {"papers": list_papers()})
        if path == "/api/reviews/due":
            return self._json(200, {"reviews": review_store.due_list()})
        if path == "/api/companion/config":
            return self._json(200, companion_config.load())
        if path == "/api/session/history":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            paper = (q.get("paper") or [""])[0]
            try:
                index = int((q.get("index") or ["0"])[0])
            except (TypeError, ValueError):
                return self._json(400, {"error": "bad index"})
            if not paper:
                return self._json(400, {"error": "paper required"})
            hist = session_store.history_for_problem(paper, index)
            events = review_store.ratings_for_problem(paper, index)
            for batch in hist.get("batches") or []:
                hit = None
                for ev in events:
                    if ev.get("session_id") == batch.get("id"):
                        hit = ev
                        break
                    if not ev.get("session_id") and batch.get("ended_at"):
                        if abs(int(ev.get("at") or 0) - int(batch["ended_at"])) <= 120:
                            hit = ev
                if hit:
                    batch["rating"] = hit.get("rating")
                    batch["rated_at"] = hit.get("at")
            return self._json(200, hist)
        if path == "/api/sessions/recent":
            rows = session_store.recent(10)
            for row in rows:
                try:
                    app_api.save_session(row)
                except Exception:
                    pass
            return self._json(200, {"sessions": rows})
        if path == "/api/db/summary":
            return self._json(200, {"tables": appdb.summary()})
        if path == "/api/app/overview":
            return self._json(200, app_api.overview())
        if path == "/api/app/plans":
            return self._json(200, app_api.plans_tree())
        if path == "/api/app/figure":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            return self._figure_info((q.get("paper") or [""])[0], (q.get("index") or ["0"])[0])
        if path == "/api/app/vocab":
            return self._json(200, app_api.vocab_list())
        if path == "/api/app/writing":
            return self._json(200, app_api.writing_list())
        if path == "/api/app/reports":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if (q.get("archive") or [""])[0] == "1":
                try:
                    learning_report.ensure_yesterday()
                except Exception:
                    pass
            return self._json(200, {"reports": learning_report.list_reports()})
        if path == "/api/app/report":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            date = (q.get("date") or [""])[0] or time.strftime("%Y-%m-%d")
            data = learning_report.load(date)
            if not data:
                return self._json(404, {"error": "report not found", "date": date})
            return self._json(200, data)
        if path == "/api/app/writing/templates":
            return self._json(200, app_api.writing_templates())
        if path.startswith("/api/app/writing/"):
            tid = urllib.parse.unquote(path[len("/api/app/writing/"):]).strip("/")
            if tid.endswith("/report"):
                tid = tid[:-len("/report")]
                data = app_api.writing_report(tid)
                if not data:
                    return self._json(404, {"error": "writing not found"})
                return self._json(200, data)
            data = app_api.writing_get(tid)
            if not data:
                return self._json(404, {"error": "writing not found"})
            return self._json(200, data)
        if path == "/api/app/due":
            return self._json(200, app_api.due_list())
        if path == "/api/app/time":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            day = (q.get("date") or [None])[0]
            return self._json(200, app_api.get_time(day))
        if path.startswith("/api/app/problem/"):
            rest = urllib.parse.unquote(path[len("/api/app/problem/"):]).strip("/")
            parts = rest.rsplit("/", 2)
            if len(parts) == 3 and parts[2] in ("next", "prev"):
                try:
                    item = (app_api.next_from_problem if parts[2] == "next" else app_api.previous_before)(
                        parts[0], int(parts[1]))
                except (TypeError, ValueError):
                    return self._json(400, {"error": "bad problem"})
                if not item:
                    return self._json(404, {"error": "no " + parts[2] + " problem"})
                return self._json(200, {"ok": True, parts[2]: item})
        if path.startswith("/api/app/plan/"):
            pid = urllib.parse.unquote(path[len("/api/app/plan/"):]).strip("/")
            if pid.endswith("/next"):
                pid = pid[:-len("/next")]
                nxt = app_api.next_problem(pid)
                if not nxt:
                    return self._json(404, {"error": "no next problem"})
                return self._json(200, {"ok": True, "next": nxt})
            data = app_api.plan_detail(pid)
            if not data:
                return self._json(404, {"error": "plan not found"})
            return self._json(200, data)
        if path.startswith("/api/session/"):
            sid = urllib.parse.unquote(path[len("/api/session/"):]).strip("/")
            data = session_store.get(sid)
            if not data:
                return self._json(404, {"error": "session not found"})
            try:
                app_api.save_session(data)
            except Exception:
                pass
            return self._json(200, data)
        if path.startswith("/api/paper/"):
            pid = urllib.parse.unquote(path[len("/api/paper/"):]).strip("/")
            d = paper_dir(pid)
            data = app_api.paper_detail(pid)
            if data:
                stamp = int(os.path.getmtime(os.path.join(d, "result.json"))) if d and os.path.isfile(os.path.join(d, "result.json")) else 0
                for i, p in enumerate(data.get("problems") or []):
                    p["index"] = i
                    p["text"] = html.unescape(str(p.get("text") or ""))
                    for o in p.get("options") or []:
                        if isinstance(o, dict):
                            o["text"] = html.unescape(str(o.get("text") or ""))
                            if o.get("image"):
                                rel = str(o["image"]).replace("\\", "/")
                                o["image_url"] = "/media/%s/%s?t=%s" % (pid, rel, stamp)
                    p["text_trusted"] = True
                    page = p.get("page") or 1
                    page_file = os.path.join(d, "pages", "page-%02d.jpg" % page) if d else ""
                    p["page_url"] = "/media/%s/pages/page-%02d.jpg?t=%s" % (pid, page, stamp) \
                        if page_file and os.path.isfile(page_file) else ""
                    rel = str(p.get("crop") or "").replace("\\", "/")
                    crop_file = os.path.join(d, rel) if d and rel else ""
                    p["crop_url"] = "/media/%s/%s?t=%s" % (pid, rel, stamp) \
                        if crop_file and os.path.isfile(crop_file) else ""
                    p["image_url"] = p["page_url"]
                return self._json(200, data)
            if not d:
                return self._json(404, {"error": "paper not found"})
            with open(os.path.join(d, "result.json"), encoding="utf-8") as f:
                r = json.load(f)
            for i, p in enumerate(r.get("problems") or []):
                p["index"] = i
                p["text"] = html.unescape(str(p.get("text") or ""))
                for o in p.get("options") or []:
                    if isinstance(o, dict):
                        o["text"] = html.unescape(str(o.get("text") or ""))
                p["text_trusted"] = p.get("text_trusted", True) is not False
                stamp = int(os.path.getmtime(os.path.join(d, "result.json")))
                rel = str(p.get("retake") or ("pages/page-%02d.jpg" % p.get("page", 1))).replace("\\", "/")
                rel_file = os.path.join(d, rel)
                p["image_url"] = "/media/%s/%s?t=%s" % (pid, rel, stamp) \
                    if os.path.isfile(rel_file) else ""
                page_file = os.path.join(d, "pages", "page-%02d.jpg" % p.get("page", 1))
                p["page_url"] = "/media/%s/pages/page-%02d.jpg?t=%s" % (pid, p.get("page", 1), stamp) \
                    if os.path.isfile(page_file) else ""
                rel_crop = str(p.get("crop") or ("crops/p%02d.jpg" % (i + 1))).replace("\\", "/")
                crop_file = os.path.join(d, rel_crop)
                p["crop_url"] = "/media/%s/%s?t=%s" % (pid, rel_crop, stamp) \
                    if os.path.isfile(crop_file) else ""
            return self._json(200, {"id": pid, "pages": r.get("pages"), "problems": r.get("problems") or [], "warnings": r.get("warnings") or []})
        if path.startswith("/media/"):
            rest = urllib.parse.unquote(path[len("/media/"):])
            parts = rest.split("/", 1)
            if len(parts) != 2:
                return self._json(404, {"error": "not found"})
            pid, rel = parts
            d = paper_dir(pid)
            if not d:
                return self._json(404, {"error": "paper not found"})
            target = os.path.abspath(os.path.join(d, rel))
            if not target.startswith(os.path.abspath(d) + os.sep):
                return self._json(403, {"error": "forbidden"})
            return self._file(target)
        if path.startswith("/tts/"):
            name = path[len("/tts/"):]
            base = os.path.abspath(os.path.join(DATA, "tts"))
            target = os.path.abspath(os.path.join(base, name))
            if not target.startswith(base + os.sep) or not os.path.isfile(target):
                return self._json(404, {"error": "not found"})
            return self._file(target)
        if path.startswith("/katex/"):
            name = path[len("/katex/"):]
            base = os.path.abspath(os.path.join(os.path.dirname(ROOT), "app", "素材", "katex"))
            target = os.path.abspath(os.path.join(base, name))
            if not target.startswith(base + os.sep) or not os.path.isfile(target):
                return self._json(404, {"error": "not found"})
            return self._file(target)
        if path == "/voices.html":
            return self._file(os.path.join(WEB, "voices.html"))
        if path.startswith("/audio/"):
            name = path[len("/audio/"):]
            base = os.path.abspath(os.path.join(WEB, "audio"))
            target = os.path.abspath(os.path.join(base, name))
            if not target.startswith(base + os.sep) or not os.path.isfile(target):
                return self._json(404, {"error": "not found"})
            return self._file(target)
        if path in ("/", "/home.html"):
            return self._file(os.path.join(WEB, "home.html"))
        if path == "/home.js":
            return self._file(os.path.join(WEB, "home.js"))
        if path in ("/report.html", "/report.js"):
            return self._file(os.path.join(WEB, path.lstrip("/")))
        if path in ("/app.css", "/plan.html", "/plan.js", "/time.html", "/time.js", "/writing.html", "/writing.js",
                    "/vocab.html", "/vocab.js", "/brand.svg"):
            return self._file(os.path.join(WEB, path.lstrip("/")))
        if path in ("/correct.html", "/index.html"):
            return self._file(os.path.join(WEB, "index.html"))
        if path in ("/talk.html", "/talk.js"):
            return self._file(os.path.join(WEB, path.lstrip("/")))
        if path in ("/app.js", "/style.css"):
            return self._file(os.path.join(WEB, path.lstrip("/")))
        return self._json(404, {"error": "not found"})

    def _load(self, d):
        with open(os.path.join(d, "result.json"), encoding="utf-8") as f:
            return json.load(f)

    def _save(self, d, result):
        with open(os.path.join(d, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    def _session(self, body):
        paper = str(body.get("paper") or "")
        d = paper_dir(paper)
        if not d:
            return self._json(404, {"error": "paper not found"})
        try:
            index = int(body.get("index"))
        except (TypeError, ValueError):
            return self._json(400, {"error": "bad index"})
        try:
            data = session_store.get_or_create(
                paper, index, body.get("mode") or "tutor", body.get("model") or ""
            )
            try:
                app_api.mark_problem_in_session(paper, index)
                app_api.save_session(data)
            except Exception:
                pass
            return self._json(200, data)
        except Exception as e:
            return self._json(500, {"error": "创建会话失败：%s" % e})

    def _asr(self, body):
        raw = str(body.get("audio") or "")
        if "," in raw:
            raw = raw.split(",", 1)[1]
        try:
            data = base64.b64decode(raw)
        except Exception:
            return self._json(400, {"error": "bad audio"})
        if len(data) < 1000:
            return self._json(400, {"error": "audio too short"})
        keep_asr_audio(data)
        d = os.path.join(DATA, "asr")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "%d.wav" % time.time_ns())
        try:
            with open(path, "wb") as f:
                f.write(data)
            if wav_peak(path) < 0.002:
                return self._json(200, {"text": "", "silent": True, "usage": {}})
            r = speech.transcribe_wav(path, body.get("context") or "")
            return self._json(200, r)
        except Exception as e:
            return self._json(500, {"error": "识别失败：%s" % e})
        finally:
            safe_remove(path)

    def _figure_info(self, paper, index):
        try:
            p = app_api.problem_at(str(paper), int(index))
        except (TypeError, ValueError):
            p = None
        if not p:
            return self._json(404, {"error": "problem not found"})
        fig = app_api.get_problem_figure(p.get("id") or "")
        if not fig:
            return self._json(200, {"ok": True, "image_url": "", "description": ""})
        path = str(fig.get("image_path") or "")
        return self._json(200, {
            "ok": True,
            "image_url": ("/media/" + urllib.parse.quote(str(paper)) + "/" + path) if path else "",
            "description": fig.get("description") or "",
        })

    def _figure_upload(self, body):
        try:
            paper = str(body.get("paper") or "")
            index = int(body.get("index"))
            d = paper_dir(paper)
            p = app_api.problem_at(paper, index)
            if not d or not p:
                return self._json(404, {"error": "problem not found"})
            action = str(body.get("action") or "upload")
            if action == "description":
                if not app_api.update_problem_figure(p.get("id") or "", str(body.get("description") or "")):
                    return self._json(404, {"error": "题图不存在"})
                return self._json(200, {"ok": True})
            if action == "delete":
                rel = app_api.delete_problem_figure(p.get("id") or "")
                if rel is None:
                    return self._json(404, {"error": "题图不存在"})
                path = os.path.abspath(os.path.join(d, rel))
                base = os.path.abspath(d)
                if path.startswith(base + os.sep) and os.path.isfile(path):
                    safe_remove(path)
                return self._json(200, {"ok": True})
            raw = str(body.get("image") or "")
            if not raw.startswith("data:image/"):
                return self._json(400, {"error": "image required"})
            head, b64 = raw.split(",", 1)
            mime = head[5:].split(";")[0]
            ext = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
                   "image/webp": "webp"}.get(mime, "png")
            data = base64.b64decode(b64)
            if len(data) > 12 * 1024 * 1024:
                return self._json(400, {"error": "image too large"})
            safe = re.sub(r"[^\w.-]+", "_", str(p.get("id") or "problem"))[:80]
            out_dir = os.path.join(d, "manual")
            os.makedirs(out_dir, exist_ok=True)
            name = safe + "." + ext
            path = os.path.join(out_dir, name)
            with open(path, "wb") as f:
                f.write(data)
            focus = "第%s题：%s" % (p.get("no") or (index + 1), str(p.get("text") or "")[:300])
            desc = vision.describe_figure(path, focus=focus)
            rel = "manual/" + name
            app_api.save_problem_figure(p.get("id") or "", rel, desc)
            return self._json(200, {
                "ok": True,
                "image_url": "/media/" + urllib.parse.quote(paper) + "/" + rel,
                "description": desc or "",
            })
        except Exception as e:
            return self._json(500, {"error": "题图识别失败：%s" % e})

    def _chat_export(self, body):
        try:
            text = str(body.get("text") or "").strip()
            if not text:
                return self._json(400, {"error": "text required"})
            title = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", str(body.get("title") or "chat")).strip("-")[:60] or "chat"
            out_dir = os.path.join(DATA, "exports")
            os.makedirs(out_dir, exist_ok=True)
            name = time.strftime("%Y%m%d-%H%M%S") + "-" + title + ".md"
            path = os.path.join(out_dir, name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return self._json(200, {"ok": True, "path": path, "name": name})
        except Exception as e:
            return self._json(500, {"error": "导出失败：%s" % e})

    def _companion_feedback(self, body):
        try:
            rid = feedback_store.add(
                body.get("paper"), body.get("index"), body.get("sessionId"),
                body.get("tags"), body.get("note") or "",
            )
            return self._json(200, {"ok": True, "id": rid})
        except Exception as e:
            return self._json(400, {"error": str(e)})

    def _preference_pair(self, body):
        try:
            text = str(body.get("text") or "").strip()
            actual = str(body.get("actual") or "").strip()
            history = list(body.get("history") or [])
            while history and (history[-1].get("role") == "assistant"):
                history.pop()
            history = slice_batch_history(history)
            if not text or not actual:
                return self._json(400, {"error": "text and actual required"})
            cfg = companion_config.load()
            extra = cfg["preference"]["variant_instruction"]
            context = str(body.get("context") or "")
            fig = _figure_description(body.get("paper"), body.get("index"))
            if fig:
                context += "\n\n题目图描述（只用于理解图形，不要复述给用户）：\n" + fig
            pid = str(body.get("paper") or "")
            idx = body.get("index")
            mode = str(body.get("mode") or "tutor")
            memory = round_memory_block(pid, idx, mode) if pid and idx is not None else ""
            if memory:
                context += "\n\n" + memory
            r = speech.chat_reply(
                text, history, context,
                body.get("model") or None, "tutor",
                body.get("subjectId") or "math2",
                body.get("problemType") or "single",
                background_only=True, extra=extra,
                history_window=cfg["chat"]["history_window"],
                temperature=cfg["chat"]["temperature"],
            )
            variant = str(r.get("text") or "").strip()
            if not variant or variant == actual:
                return self._json(200, {"ok": False, "reason": "no difference"})
            a = {"text": actual, "source": "current"}
            b = {"text": variant, "source": "less_intervention"}
            if random.random() < 0.5:
                a["text"], b["text"] = b["text"], a["text"]
                a["source"], b["source"] = b["source"], a["source"]
            return self._json(200, {
                "ok": True,
                "axis": "intervention",
                "a": a,
                "b": b,
            })
        except Exception as e:
            return self._json(500, {"error": "生成偏好对比失败：%s" % e})

    def _preference_vote(self, body):
        try:
            choice = str(body.get("choice") or "")
            rid = preference_store.vote(
                body.get("paper"), body.get("index"), body.get("sessionId"),
                body.get("axis"), body.get("optionA"), body.get("optionB"),
                body.get("aSource"), body.get("bSource"), choice,
            )
            return self._json(200, {"ok": True, "id": rid})
        except Exception as e:
            return self._json(400, {"error": str(e)})

    def _chat_background(self, body):
        """最小学伴：只给身份和题目背景，不注入教案/模式/校验规则。"""
        text = str(body.get("text") or "").strip()
        if not text:
            return self._json(400, {"error": "text required"})
        display = str(body.get("display") or "").strip() or text
        try:
            cfg = companion_config.load()
            pid = str(body.get("paper") or "")
            idx = body.get("index")
            mode = str(body.get("mode") or "tutor")
            context = str(body.get("context") or "")
            fig = _figure_description(body.get("paper"), body.get("index"))
            if fig:
                context += "\n\n题目图描述（只用于理解图形，不要复述给用户）：\n" + fig
            memory = round_memory_block(pid, idx, mode) if pid and idx is not None else ""
            if memory:
                context += "\n\n" + memory
            history = (
                current_round_history(pid, idx, body.get("history") or [])
                if pid and idx is not None
                else (body.get("history") or [])
            )
            r = speech.chat_reply(
                text,
                history,
                context,
                body.get("model") or None,
                "tutor",
                body.get("subjectId") or "math2",
                body.get("problemType") or "single",
                background_only=True,
                history_window=cfg["chat"]["history_window"],
                temperature=cfg["chat"]["temperature"],
            )
            r["mode"] = "companion"
            r["router"] = {}
            sid = str(body.get("sessionId") or "")
            if sid:
                try:
                    session_store.append(sid, "user", text, display)
                    session_store.append(sid, "assistant", r.get("text", ""), r.get("speech", ""))
                    sess = session_store.get(sid)
                    if sess:
                        app_api.save_session(sess)
                    app_api.append_turn(sid, "user", text, display)
                    app_api.append_turn(sid, "assistant", r.get("text", ""), r.get("speech", ""))
                except Exception:
                    pass
            return self._json(200, r)
        except Exception as e:
            return self._json(500, {"error": "对话失败：%s" % e})

    def _chat(self, body):
        if os.environ.get("TUTOR_BACKGROUND_ONLY", "1") != "0":
            return self._chat_background(body)
        text = str(body.get("text") or "").strip()
        if not text:
            return self._json(400, {"error": "text required"})
        display = str(body.get("display") or "").strip() or text
        context = str(body.get("context") or "")
        plan = None
        try:
            pid = str(body.get("paper") or "")
            idx = body.get("index")
            if pid and idx is not None:
                p = self._problem(pid, int(idx))
                if p:
                    plan = app_api.get_lesson_plan(p["id"])
                    if not plan:
                        plan = speech.make_lesson_plan(p, body.get("model") or None)
                        app_api.save_lesson_plan(p["id"], plan)
                    context += "\n\n【内部教案（只供安排追问，不要展示/复述给学生）】\n"
                    context += "目标：" + str(plan.get("goal") or "") + "\n"
                    context += "核心：" + "；".join(plan.get("core") or []) + "\n"
                    context += "路径：" + "；".join(plan.get("path") or []) + "\n"
                    for s in plan.get("stuck") or []:
                        context += "卡点：%s；提示：%s；提示后：%s\n" % (
                            s.get("point") or "", s.get("hint") or "", s.get("next") or "")
                    context += "同一卡点最多追问 %s 次；学生说不知道/进行不下去时，给最小提示或建议结束。\n" % (
                        plan.get("max_followups") or 2)
        except Exception:
            context = str(body.get("context") or "")
        try:
            history = body.get("history") or []
            sid = str(body.get("sessionId") or "")
            state = app_api.get_tutor_state(sid) if sid else {}
            base_mode = str(body.get("mode") or "tutor")
            route = tutor_router.route(text, history)
            role = route.get("role") or tutor_router.LISTENING
            if base_mode in ("review", "exam"):
                role = "guide"
            if role == tutor_router.LISTENING:
                r = {"text": "", "speech": "", "silent": True}
            elif role == "gap_check":
                answer = _gap_answer(history, text) or text
                if plan:
                    comparison = speech.compare_with_plan(plan, answer, body.get("model") or None)
                    text_out = _format_gap_check(comparison)
                else:
                    text_out = "还没有教案，先开始一次讲题，再做查漏。"
                r = {"text": text_out, "speech": text_out}
            else:
                mode = base_mode if base_mode in ("review", "exam") else role
                r = speech.chat_reply(
                    text,
                    history,
                    context,
                    body.get("model") or None,
                    mode,
                    body.get("subjectId") or "math2",
                    body.get("problemType") or "single",
                )
                violations = tutor_validator.validate(role, r.get("text", ""))
                if violations:
                    cleaned = tutor_validator.clean(role, r.get("text", ""))
                    if cleaned and not tutor_validator.validate(role, cleaned):
                        r["text"] = cleaned
                        r["speech"] = cleaned
                    else:
                        fallback = _role_fallback(role, plan, text, state)
                        r["text"] = fallback
                        r["speech"] = fallback
            r["mode"] = role
            r["router"] = route
            if sid:
                try:
                    state = app_api.get_tutor_state(sid) or {}
                    state["last_mode"] = role
                    state["last_router"] = route
                    state["last_valid"] = not tutor_validator.validate(role, r.get("text", ""))
                    app_api.save_tutor_state(sid, state)
                except Exception:
                    pass
            if sid:
                session_store.append(sid, "user", text, display)
                if r.get("text"):
                    session_store.append(sid, "assistant", r.get("text", ""), r.get("speech", ""))
                try:
                    sess = session_store.get(sid)
                    if sess:
                        app_api.save_session(sess)
                    app_api.append_turn(sid, "user", text, display)
                    if r.get("text"):
                        app_api.append_turn(sid, "assistant", r.get("text", ""), r.get("speech", ""))
                except Exception:
                    pass
            return self._json(200, r)
        except Exception as e:
            return self._json(500, {"error": "对话失败：%s" % e})

    def _normalize(self, body):
        text = str(body.get("text") or "").strip()
        if not text:
            return self._json(400, {"error": "text required"})
        try:
            return self._json(200, speech.normalize_transcript(text, body.get("model") or None, body.get("context") or ""))
        except Exception as e:
            return self._json(500, {"error": "整理失败：%s" % e})

    def _tts(self, body):
        text = str(body.get("text") or "").strip()
        if not text:
            return self._json(400, {"error": "text required"})
        try:
            r = speech.synth_wav(
                text, os.path.join(DATA, "tts"),
                provider=body.get("provider"), voice=body.get("voice"),
            )
            return self._json(200, {"url": "/tts/" + r["file"], "usage": r.get("usage", {})})
        except Exception as e:
            return self._json(500, {"error": "合成失败：%s" % e})

    def _problem(self, pid, idx):
        p = app_api.problem_at(pid, idx)
        if p:
            c = appdb.connect()
            try:
                row = c.execute("SELECT reference_answer FROM problems WHERE id=?", (p.get("id"),)).fetchone()
                if row:
                    p["reference_answer"] = row["reference_answer"] or ""
            finally:
                c.close()
            return p
        d = paper_dir(pid)
        if not d:
            return None
        return self._load(d)["problems"][idx]

    def _finish(self, body):
        pid = str(body.get("paper") or "")
        try:
            idx = int(body.get("index"))
            p = self._problem(pid, idx)
            if not p:
                raise KeyError("problem")
        except (KeyError, IndexError, TypeError, ValueError):
            return self._json(404 if not paper_dir(pid) else 400, {"error": "bad index"})
        try:
            history = current_round_history(pid, idx, body.get("history") or [])
            summary = speech.summarize_problem(p, history, body.get("model") or None)
            try:
                summary = speech.merge_finish_check(summary, app_api.get_lesson_plan(p["id"]))
            except Exception:
                pass
            item = review_store.upsert(pid, idx, p.get("no"), p.get("text"), summary)
            return self._json(200, {
                "ok": True,
                "id": item["id"],
                "summary": summary,
                "suggested": summary["suggested"],
                "due": item["fsrs"].get("due"),
            })
        except Exception as e:
            return self._json(500, {"error": "收尾失败：%s" % e})

    def _cleanup_finish(self):
        now = time.time()
        for fid, item in list(FINISH_SESSIONS.items()):
            if now - item.get("created", 0) > FINISH_TTL:
                FINISH_SESSIONS.pop(fid, None)

    def _finish_start(self, body):
        self._cleanup_finish()
        pid = str(body.get("paper") or "")
        try:
            idx = int(body.get("index"))
            p = self._problem(pid, idx)
            if not p:
                raise KeyError("problem")
        except (KeyError, IndexError, TypeError, ValueError):
            return self._json(404 if not paper_dir(pid) else 400, {"error": "bad index"})
        try:
            history = current_round_history(pid, idx, body.get("history") or [])
            rubric = speech.summarize_problem(p, history, body.get("model") or None)
            try:
                rubric = speech.merge_finish_check(rubric, app_api.get_lesson_plan(p["id"]))
            except Exception:
                pass
            parts = []
            if rubric.get("outline"):
                parts.append("思路：" + str(rubric.get("outline")))
            if rubric.get("stuck"):
                parts.append("卡点：" + str(rubric.get("stuck")))
            if rubric.get("pitfalls"):
                parts.append("易错：" + str(rubric.get("pitfalls")))
            auto_summary = "\n".join(parts).strip()
            fid = uuid.uuid4().hex
            FINISH_SESSIONS[fid] = {
                "paper": pid,
                "index": idx,
                "no": p.get("no"),
                "text": p.get("text"),
                "rubric": rubric,
                "summary": "",
                "rounds": 0,
                "created": time.time(),
            }
            return self._json(200, {
                "id": fid,
                "summary": auto_summary,
                "suggested": rubric.get("suggested") or "good",
                "reason": rubric.get("reason") or "",
                "question": "",
            })
        except Exception as e:
            return self._json(500, {"error": "收尾准备失败：%s" % e})

    def _finish_summary(self, body):
        self._cleanup_finish()
        fid = str(body.get("id") or "")
        state = FINISH_SESSIONS.get(fid)
        if not state:
            return self._json(404, {"error": "收尾会话已过期，请重开"})
        summary = str(body.get("summary") or "").strip()
        if not summary:
            return self._json(400, {"error": "总结为空"})
        if state["rounds"] >= 1:
            state["summary"] = summary
            return self._json(200, {"done": True, "question": ""})
        try:
            r = speech.evaluate_summary(state["rubric"], summary)
            state["rounds"] += 1
            if r.get("done"):
                state["summary"] = summary
            return self._json(200, r)
        except Exception as e:
            return self._json(500, {"error": "收尾比较失败：%s" % e})

    def _finish_complete(self, body):
        fid = str(body.get("id") or "")
        state = FINISH_SESSIONS.get(fid)
        if not state:
            return self._json(404, {"error": "收尾会话已过期，请重开"})
        summary = str(body.get("summary") or state.get("summary") or "").strip()
        if not summary:
            return self._json(400, {"error": "还没有你的总结"})
        try:
            rubric = state["rubric"]
            stored = {
                "user": summary,
                "suggested": rubric.get("suggested") or "good",
                "reason": rubric.get("reason") or "",
            }
            item = review_store.upsert(state["paper"], state["index"], state["no"], state["text"], stored)
            app_api.sync_review(item["id"], item["fsrs"], stored)
            try:
                app_api.set_problem_status(item["id"], "scheduled")
            except Exception:
                pass
            # 把学伴总结留在这道题的对话里，之后重进/刷新还能看到
            try:
                sid = session_store.history_for_problem(state["paper"], state["index"]).get("sessionId")
                if sid:
                    turns = (session_store.get(sid) or {}).get("turns") or []
                    last = turns[-1] if turns else None
                    if not (last and last.get("role") == "summary" and last.get("content") == summary):
                        session_store.append(sid, "summary", summary)
                        app_api.append_turn(sid, "summary", summary)
                        sess = session_store.get(sid)
                        if sess:
                            app_api.save_session(sess)
            except Exception:
                pass
            FINISH_SESSIONS.pop(fid, None)
            return self._json(200, {
                "ok": True,
                "id": item["id"],
                "suggested": stored["suggested"],
                "reason": stored["reason"],
            })
        except Exception as e:
            return self._json(500, {"error": "收尾保存失败：%s" % e})

    def _compare(self, body):
        pid = str(body.get("paper") or "")
        try:
            idx = int(body.get("index"))
            p = self._problem(pid, idx)
            if not p:
                raise KeyError("problem")
        except (KeyError, IndexError, TypeError, ValueError):
            return self._json(404, {"error": "bad problem"})
        plan = app_api.get_lesson_plan(p["id"])
        if not plan:
            return self._json(409, {"error": "还没有教案，先开始一次讲题"})
        try:
            result = speech.compare_with_plan(plan, body.get("answer") or "", body.get("model") or None)
            return self._json(200, {"ok": True, "comparison": result})
        except Exception as e:
            return self._json(500, {"error": "对比失败：%s" % e})

    def _report_generate(self, body):
        date = str(body.get("date") or time.strftime("%Y-%m-%d"))
        try:
            r = learning_report.generate(
                date,
                model=body.get("model") or None,
                with_polish=bool(body.get("polish", True)),
            )
            return self._json(200, {"ok": True, "date": date, "report": r["report"], "raw": r["raw"]})
        except Exception as e:
            return self._json(500, {"error": "生成报告失败：%s" % e})

    def _review(self, body):
        try:
            rid = str(body.get("id") or "")
            rating = body.get("rating")
            result = review_store.rate(rid, rating, body.get("sessionId") or "")
            item = review_store.get(rid)
            if item:
                app_api.sync_review(rid, item.get("fsrs") or {}, item.get("summary") or {}, rating)
            return self._json(200, result)
        except KeyError:
            return self._json(404, {"error": "review not found"})
        except Exception as e:
            return self._json(400, {"error": str(e)})

    def _reread(self, d, body):
        try:
            idx = int(body.get("index"))
            result = self._load(d)
            p = result["problems"][idx]
        except (KeyError, IndexError, TypeError, ValueError):
            return self._json(400, {"error": "bad index"})
        try:
            if p.get("retake"):
                src = os.path.join(d, p["retake"])
            else:
                page = os.path.join(d, "pages", "page-%02d.jpg" % p.get("page", 1))
                if not p.get("bbox"):
                    return self._json(400, {"error": "missing bbox"})
                src = os.path.join(d, "crops", "p%02d-reread.jpg" % (idx + 1))
                ingest.crop_problem(page, p["bbox"], src)
            info = vision.read_problem(src)
            p["text"] = info["text"]
            p["options"] = info["options"]
            p["latex"] = info["latex"]
            p["text_trusted"] = True
            p["reread_at"] = int(time.time())
            self._save(d, result)
            return self._json(200, {"ok": True, "problem": p, "usage": info.get("usage", {})})
        except Exception as e:
            return self._json(500, {"error": "重读失败：%s" % e})

    def _retake(self, d, body):
        try:
            idx = int(body.get("index"))
            raw = str(body.get("image") or "")
            if "," in raw:
                raw = raw.split(",", 1)[1]
            data = base64.b64decode(raw)
            if not data:
                raise ValueError("empty image")
            result = self._load(d)
            p = result["problems"][idx]
        except Exception:
            return self._json(400, {"error": "bad index or image"})
        os.makedirs(os.path.join(d, "retakes"), exist_ok=True)
        rel = os.path.join("retakes", "p%02d.jpg" % (idx + 1))
        with open(os.path.join(d, rel), "wb") as f:
            f.write(data)
        p["retake"] = rel
        p["bbox"] = [0, 0, 1, 1]
        p["text_trusted"] = False
        warning = ""
        try:
            info = vision.read_problem(os.path.join(d, rel))
            p["text"] = info["text"]
            p["options"] = info["options"]
            p["latex"] = info["latex"]
            p["text_trusted"] = True
        except Exception as e:
            warning = "重拍已保存，但自动重读失败：%s" % e
        self._save(d, result)
        return self._json(200, {"ok": True, "problem": p, "warning": warning})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        m_end = re.match(r"^/api/session/([^/]+)/end$", path)
        m_rollback = re.match(r"^/api/session/([^/]+)/rollback$", path)
        if path == "/api/session" or m_end or m_rollback:
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            except Exception:
                return self._json(400, {"error": "invalid json"})
            if m_end:
                sid = urllib.parse.unquote(m_end.group(1))
                session_store.end(sid)
                try:
                    app_api.end_session(sid)
                except Exception:
                    pass
                return self._json(200, {"ok": True})
            if m_rollback:
                sid = urllib.parse.unquote(m_rollback.group(1))
                try:
                    data = session_store.rollback_at(sid, int(body.get("index")))
                    if not data:
                        return self._json(404, {"error": "session not found"})
                    app_api.replace_session_turns(sid, data.get("turns") or [])
                    return self._json(200, {"ok": True, "session": data})
                except (TypeError, ValueError):
                    return self._json(400, {"error": "bad turn index"})
                except Exception as e:
                    return self._json(500, {"error": "回退失败：%s" % e})
            return self._session(body)
        if path.startswith("/api/app/queue/"):
            qid = urllib.parse.unquote(path[len("/api/app/queue/"):]).strip("/")
            if qid.endswith("/open"):
                qid = qid[:-len("/open")]
                data = app_api.queue_open(qid)
            elif qid.endswith("/done"):
                qid = qid[:-len("/done")]
                data = app_api.queue_done(qid)
            else:
                return self._json(404, {"error": "not found"})
            if not data:
                return self._json(404, {"error": "queue item not found"})
            return self._json(200, {"ok": True, "item": data})
        if path.startswith("/api/app/writing/"):
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            except Exception:
                return self._json(400, {"error": "invalid json"})
            tid = urllib.parse.unquote(path[len("/api/app/writing/"):]).strip("/")
            try:
                if tid.endswith("/feedback"):
                    tid = tid[:-len("/feedback")]
                    data = app_api.writing_feedback(tid, body.get("draft"))
                elif tid.endswith("/final"):
                    tid = tid[:-len("/final")]
                    data = app_api.writing_final(tid, body.get("draft"))
                else:
                    data = app_api.writing_save(tid, str(body.get("draft") or ""))
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            except Exception as e:
                return self._json(500, {"error": "写作批改失败：%s" % e})
            if not data:
                return self._json(404, {"error": "writing not found"})
            return self._json(200, data)
        if path == "/api/app/vocab":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            except Exception:
                return self._json(400, {"error": "invalid json"})
            action = str(body.get("action") or "add")
            if action == "add":
                data = app_api.vocab_add(body.get("word"), body.get("sentence"), body.get("paperId"))
            elif action == "status":
                data = app_api.vocab_set_status(str(body.get("id") or ""), str(body.get("status") or ""))
            elif action == "delete":
                data = app_api.vocab_delete(str(body.get("id") or ""))
            else:
                return self._json(400, {"error": "bad action"})
            status = data.pop("status", 200) if isinstance(data, dict) else 500
            return self._json(status, data)
        if path == "/api/app/plan/unit":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            except Exception:
                return self._json(400, {"error": "invalid json"})
            data = app_api.set_unit_status(str(body.get("unitId") or ""), str(body.get("status") or ""))
            status = data.pop("status", 200) if isinstance(data, dict) else 500
            return self._json(status, data)
        if path == "/api/app/plan/active":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            except Exception:
                return self._json(400, {"error": "invalid json"})
            data = app_api.set_active_plan(str(body.get("planId") or ""))
            status = data.pop("status", 200) if isinstance(data, dict) else 500
            return self._json(status, data)
        if path == "/api/app/plan/status":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            except Exception:
                return self._json(400, {"error": "invalid json"})
            data = app_api.set_plan_status(str(body.get("planId") or ""), str(body.get("status") or ""))
            status = data.pop("status", 200) if isinstance(data, dict) else 500
            return self._json(status, data)
        if path == "/api/app/position":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            except Exception:
                return self._json(400, {"error": "invalid json"})
            paper = str(body.get("paper") or "").strip()
            if not paper:
                return self._json(400, {"error": "paper required"})
            try:
                index = int(body.get("index") or 0)
            except (TypeError, ValueError):
                index = 0
            try:
                return self._json(200, {"ok": bool(app_api.save_last_position(paper, index))})
            except Exception as e:
                return self._json(500, {"error": str(e)})
        if path == "/api/app/paper/assign":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            except Exception:
                return self._json(400, {"error": "invalid json"})
            data = app_api.assign_paper(str(body.get("paperId") or ""), str(body.get("planId") or ""))
            status = data.pop("status", 200) if isinstance(data, dict) else 500
            return self._json(status, data)
        if path in ("/api/app/time", "/api/app/time/confirm"):
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            except Exception:
                return self._json(400, {"error": "invalid json"})
            if path.endswith("/confirm"):
                return self._json(200, app_api.confirm_time(body.get("date")))
            try:
                minutes = int(body.get("available_min") or 180)
            except (TypeError, ValueError):
                return self._json(400, {"error": "bad available_min"})
            return self._json(200, app_api.generate_time(body.get("date"), minutes))
        if path in ("/api/asr", "/api/chat", "/api/tts", "/api/normalize", "/api/finish", "/api/finish/start", "/api/finish/summary", "/api/finish/complete", "/api/review", "/api/app/compare", "/api/app/report/generate", "/api/preference/pair", "/api/preference/vote", "/api/companion/feedback", "/api/chat/export", "/api/app/figure"):
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > 16 * 1024 * 1024:
                    raise ValueError("bad length")
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                return self._json(400, {"error": "invalid json"})
            if path == "/api/asr":
                return self._asr(body)
            if path == "/api/chat":
                return self._chat(body)
            if path == "/api/normalize":
                return self._normalize(body)
            if path == "/api/finish":
                return self._finish(body)
            if path == "/api/finish/start":
                return self._finish_start(body)
            if path == "/api/finish/summary":
                return self._finish_summary(body)
            if path == "/api/finish/complete":
                return self._finish_complete(body)
            if path == "/api/app/compare":
                return self._compare(body)
            if path == "/api/app/report/generate":
                return self._report_generate(body)
            if path == "/api/review":
                return self._review(body)
            if path == "/api/app/figure":
                return self._figure_upload(body)
            if path == "/api/chat/export":
                return self._chat_export(body)
            if path == "/api/companion/feedback":
                return self._companion_feedback(body)
            if path == "/api/preference/pair":
                return self._preference_pair(body)
            if path == "/api/preference/vote":
                return self._preference_vote(body)
            return self._tts(body)
        m = re.match(r"^/api/paper/([^/]+)/(save|reread|retake)$", path)
        if not m:
            return self._json(404, {"error": "not found"})
        pid, action = urllib.parse.unquote(m.group(1)), m.group(2)
        d = paper_dir(pid)
        if not d:
            return self._json(404, {"error": "paper not found"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 12 * 1024 * 1024:
                raise ValueError("bad length")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return self._json(400, {"error": "invalid json"})
        if action == "reread":
            return self._reread(d, body)
        if action == "retake":
            return self._retake(d, body)
        if action == "asr":
            return self._asr(body)
        if action == "chat":
            return self._chat(body)
        if action == "tts":
            return self._tts(body)
        problems = body.get("problems")
        if not isinstance(problems, list):
            return self._json(400, {"error": "problems required"})
        result_path = os.path.join(d, "result.json")
        with open(result_path, encoding="utf-8") as f:
            result = json.load(f)
        pages = result.get("pages") or 1
        cleaned = []
        for i, p in enumerate(problems):
            if not isinstance(p, dict):
                continue
            item = {
                "no": str(p.get("no") or (i + 1)),
                "text": str(p.get("text") or ""),
                "options": p.get("options") if isinstance(p.get("options"), list) else [],
                "latex": str(p.get("latex") or ""),
                "bbox": p.get("bbox"),
                "page": int(p.get("page") or 1),
                "continues_next": bool(p.get("continues_next")),
                "merged_from_next": bool(p.get("merged_from_next")),
                "page_fragments": p.get("page_fragments") or [],
                "text_trusted": p.get("text_trusted", True) is not False,
                "retake": p.get("retake") or None,
                "cross_page": bool(p.get("cross_page")),
                "crop": p.get("crop") or None,
            }
            if not (1 <= item["page"] <= pages):
                item["page"] = 1
            cleaned.append(item)
        result["problems"] = cleaned
        result["warnings"] = []
        for i, p in enumerate(cleaned):
            if p.get("cross_page") and p.get("crop"):
                continue
            page_path = os.path.join(d, p["retake"]) if p.get("retake") else os.path.join(d, "pages", "page-%02d.jpg" % p["page"])
            if p.get("bbox") and os.path.exists(page_path):
                crop = os.path.join(d, "crops", "p%02d.jpg" % (i + 1))
                try:
                    ingest.crop_problem(page_path, p["bbox"], crop)
                    p["crop"] = os.path.relpath(crop, d)
                except Exception as e:
                    result["warnings"].append("第 %s 题裁图失败：%s" % (p["no"], e))
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return self._json(200, {"ok": True, "problems": len(cleaned)})


def main():
    appdb.init()
    local_tts.warm()
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("tutor review server")
    print("  web:  http://127.0.0.1:%d/" % PORT)
    print("  samples: " + SAMPLES)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
