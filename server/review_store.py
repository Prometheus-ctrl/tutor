#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本题级 FSRS 存储：tutor/data/reviews.json。

FSRS 对象是“整题复述”，不是知识点卡。
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "vendor"))
from fsrs import Card, Rating, Scheduler  # noqa: E402

DATA = os.path.join(os.path.dirname(HERE), "data")
STORE = os.path.join(DATA, "reviews.json")
RATINGS = {"again": 1, "hard": 2, "good": 3, "easy": 4}


def _load():
    try:
        with open(STORE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("reviews", [])
    return data


def _save(data):
    os.makedirs(DATA, exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STORE)


def _find(data, rid):
    for item in data["reviews"]:
        if item.get("id") == rid:
            return item
    return None


def _card_dict(card):
    d = card.to_dict()
    d["state_name"] = card.state.name.lower()
    return d


def upsert(paper, index, no, text, summary):
    data = _load()
    rid = "%s:%d" % (paper, index)
    item = _find(data, rid)
    now = int(time.time())
    if item is None:
        item = {
            "id": rid,
            "paper": paper,
            "index": index,
            "no": str(no or (index + 1)),
            "text": str(text or ""),
            "created": now,
            "fsrs": _card_dict(Card()),
        }
        data["reviews"].append(item)
    item["text"] = str(text or "")
    item["summary"] = summary
    item["updated"] = now
    _save(data)
    return item


def get(rid):
    return _find(_load(), str(rid))


def rate(rid, rating, session_id=""):
    rating = str(rating or "").lower()
    if rating not in RATINGS:
        raise ValueError("rating must be again/hard/good/easy")
    data = _load()
    item = _find(data, rid)
    if item is None:
        raise KeyError("review not found")
    card = Card.from_dict(item["fsrs"])
    scheduler = Scheduler(learning_steps=(), relearning_steps=())
    new_card, _log = scheduler.review_card(card, Rating(RATINGS[rating]))
    now = int(time.time())
    item["fsrs"] = _card_dict(new_card)
    item["last_rating"] = rating
    item["last_review"] = now
    item.setdefault("history", []).append({
        "rating": rating,
        "at": now,
        "session_id": str(session_id or ""),
    })
    _save(data)
    due = new_card.due
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    days = max(0.0, (due - datetime.now(timezone.utc)).total_seconds() / 86400)
    return {
        "id": rid,
        "rating": rating,
        "due": due.isoformat(),
        "interval_days": round(days, 2),
        "state": new_card.state.name.lower(),
        "stability": new_card.stability,
        "difficulty": new_card.difficulty,
    }


def ratings_for_problem(paper, index):
    """返回这道题每次评级的记录；旧数据只有最后一次，也兼容。"""
    data = _load()
    out = []
    for item in data["reviews"]:
        if item.get("paper") != str(paper) or int(item.get("index", -1)) != int(index):
            continue
        hist = item.get("history") or []
        if hist:
            out.extend(hist)
        elif item.get("last_rating") and item.get("last_review"):
            out.append({
                "rating": item.get("last_rating"),
                "at": item.get("last_review"),
                "session_id": "",
            })
    return out


def due_list():
    data = _load()
    now = datetime.now(timezone.utc)
    out = []
    for item in data["reviews"]:
        try:
            due = datetime.fromisoformat(item["fsrs"]["due"])
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            continue
        if due <= now:
            out.append({
                "id": item.get("id"),
                "no": item.get("no"),
                "paper": item.get("paper"),
                "index": item.get("index"),
                "due": due.isoformat(),
                "summary": item.get("summary") or {},
            })
    out.sort(key=lambda x: x["due"])
    return out
