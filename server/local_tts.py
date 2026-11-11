"""本地 Serena TTS 服务的生命周期管理。

讲题服务启动时后台预热；本地 TTS 请求前再检查一次。
服务掉线或机器重启后，下一次请求会自动把它拉起来。
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TTS_DIR = os.path.join(ROOT, "tts", "qwen3")
TTS_SERVER = os.path.join(TTS_DIR, "tts_server.py")
TTS_PY = os.path.join(TTS_DIR, ".venv", "Scripts", "python.exe")
TTS_URL = os.environ.get("TUTOR_TTS_LOCAL_URL", "http://127.0.0.1:8794").rstrip("/")
LOG_PATH = os.path.join(ROOT, "data", "tts", "tts-server.log")

_lock = threading.Lock()
_proc = None
_last_start = 0.0


def healthy(timeout=1.5):
    try:
        with urllib.request.urlopen(TTS_URL + "/health", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return bool(data.get("ok"))
    except Exception:
        return False


def _spawn():
    global _proc, _last_start
    if healthy():
        return True
    if not os.path.isfile(TTS_PY) or not os.path.isfile(TTS_SERVER):
        return False
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    log = open(LOG_PATH, "ab", buffering=0)
    _proc = subprocess.Popen(
        [TTS_PY, TTS_SERVER],
        cwd=TTS_DIR,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=flags,
    )
    _last_start = time.time()
    return True


def ensure(wait=60):
    """确保本地 TTS 在线；返回是否可用。"""
    if healthy():
        return True
    with _lock:
        if healthy():
            return True
        # 避免短时间内重复拉起同一个正在加载的进程
        if _proc is not None and _proc.poll() is None and time.time() - _last_start < wait:
            pass
        elif not _spawn():
            return False
        deadline = time.time() + wait
        while time.time() < deadline:
            if healthy():
                return True
            if _proc is not None and _proc.poll() is not None:
                return False
            time.sleep(1)
    return healthy()


def warm():
    if os.environ.get("TUTOR_TTS_PROVIDER", "local").strip().lower() != "local":
        return
    threading.Thread(target=ensure, kwargs={"wait": 90}, daemon=True).start()
