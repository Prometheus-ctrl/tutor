#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0 号验证 A：用 Qwen-VL 对一张试卷照片做切题，输出严格 JSON。

用法：
  python spike_vision.py [图片路径]
  不带路径时生成一张合成试卷图，只验证 API/提示词/JSON 是否通。

Key 读取顺序：DASHSCOPE_API_KEY 环境变量；Windows 用户环境变量（setx 后当前进程可能还没继承）。
结果写到 samples/spike-result.json，不打印 key。
"""
import base64
import json
import os
import sys
import urllib.request
import urllib.error

BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
MODEL = os.environ.get("TUTOR_VL_MODEL", "qwen3-vl-plus")
ROOT = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(os.path.dirname(ROOT), "samples")


def get_key():
    key = (os.environ.get("DASHSCOPE_API_KEY") or "").strip()
    if key:
        return key
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
                val, _ = winreg.QueryValueEx(k, "DASHSCOPE_API_KEY")
                return str(val or "").strip()
        except OSError:
            pass
    return ""


def synth_page(path):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1000, 1400), "white")
    d = ImageDraw.Draw(img)
    font_path = r"C:\Windows\Fonts\msyh.ttc"
    title = ImageFont.truetype(font_path, 34) if os.path.exists(font_path) else ImageFont.load_default()
    body = ImageFont.truetype(font_path, 26) if os.path.exists(font_path) else ImageFont.load_default()
    d.text((60, 50), "数学练习（合成测试页）", font=title, fill="black")
    lines = [
        "1. 求极限 lim(x→0) (sin x - x) / x^3。",
        "2. 设 f(x)=x^2 ln(1+x)，求 f'(0)。",
        "3. 讨论函数 y = x / (1 + x^2) 的单调区间与极值。",
    ]
    y = 150
    for line in lines:
        d.text((60, y), line, font=body, fill="black")
        y += 180
    img.save(path, quality=90)
    return path


def main():
    os.makedirs(SAMPLES, exist_ok=True)
    img_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SAMPLES, "synthetic-page.jpg")
    if not os.path.exists(img_path):
        synth_page(img_path)
        print("已生成合成页：" + img_path)

    key = get_key()
    if not key:
        print("缺少 DASHSCOPE_API_KEY：先 setx DASHSCOPE_API_KEY \"...\"，再重开终端")
        return 2

    with open(img_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    prompt = (
        "你是数学试卷切题助手。识别整页试卷，按题号切分，输出严格 JSON，不要 Markdown。\n"
        "每题必须包含题干和 A/B/C/D 四个选项（如果有），不要把选项漏掉。\n"
        "JSON 结构：{\"problems\":[{\"no\":\"1\",\"text\":\"题干文字\",\"options\":[{\"label\":\"A\",\"text\":\"选项内容\"}],"
        "\"latex\":\"题干公式的 LaTeX（没有就空字符串）\",\"bbox\":[x1,y1,x2,y2],\"continues_next\":false}],"
        "\"leading_continuation\":{\"text\":\"页面顶部无题号的续块\",\"options\":[{\"label\":\"C\",\"text\":\"选项内容\"}],"
        "\"bbox\":[x1,y1,x2,y2],\"continues_prev\":true}}\n"
        "如果页面顶部有上一题的无编号续块（常见是 C/D 选项），必须放进 leading_continuation，不能丢；没有就填 null。\n"
        "bbox 用 0~1 相对坐标，覆盖从题号到最后一个选项的整块；跨页题在页尾标 continues_next=true；只输出 JSON。"
    )
    body = {
        "model": MODEL,
        "temperature": 0,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
            ],
        }],
    }
    req = urllib.request.Request(
        BASE,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read().decode("utf-8")
            status = r.status
    except urllib.error.HTTPError as e:
        print("HTTP " + str(e.code))
        print(e.read().decode("utf-8", "replace")[:1500])
        return 1
    except Exception as e:
        print("请求失败：" + repr(e))
        return 1

    data = json.loads(raw)
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = data.get("usage", {})
    out = {"model": MODEL, "status": status, "image": os.path.basename(img_path), "usage": usage, "content": content}
    out_path = os.path.join(SAMPLES, "spike-result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("HTTP %s · usage=%s" % (status, json.dumps(usage, ensure_ascii=False)))
    print("返回前 1200 字：")
    print(content[:1200])
    print("完整结果：" + out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
