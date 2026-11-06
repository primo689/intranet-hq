"""Intranet HQ: a small self-hosted intranet homepage for a business or ministry.

Pipeline board, common links, and a daily brief that is generated once a day
and cached, so opening the page never costs API tokens.
"""
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, date

from flask import Flask, jsonify, request, send_from_directory, send_file

import brief as brief_mod
from store import Store

DATA_DIR = os.environ.get("DATA_DIR", "/data")
store = Store(DATA_DIR)

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

STAGES = ["Idea", "Building", "Testing", "Submitted", "Live"]


def now_local():
    return datetime.now(brief_mod.tz())


def public_settings():
    s = store.settings()
    key = s.get("anthropic_api_key") or ""
    out = {k: v for k, v in s.items() if k not in ("anthropic_api_key", "ical_url")}
    out["has_api_key"] = bool(key)
    out["api_key_hint"] = ("..." + key[-4:]) if len(key) > 8 else ""
    out["has_ical_url"] = bool(s.get("ical_url"))
    out["has_logo"] = logo_path() is not None
    return out


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/healthz")
def healthz():
    return "ok"


@app.get("/api/state")
def state():
    today = now_local().date().isoformat()
    return jsonify(
        pipeline=store.pipeline(),
        stages=STAGES,
        links=store.links(),
        brief=store.brief(today) or store.latest_brief(),
        today=today,
        settings=public_settings(),
        usage=store.usage(now_local().strftime("%Y-%m")),
    )


# ---------- pipeline ----------

def clean_app(body, existing=None):
    a = dict(existing or {})
    for field in ("name", "tagline", "next_step", "notes"):
        if field in body:
            a[field] = str(body[field])[:500].strip()
    if "stage" in body and body["stage"] in STAGES:
        a["stage"] = body["stage"]
    a["updated"] = now_local().isoformat(timespec="seconds")
    return a


@app.post("/api/pipeline")
def add_app():
    body = request.get_json(force=True) or {}
    if not str(body.get("name", "")).strip():
        return jsonify(error="Name is required"), 400
    a = clean_app(body, {"id": uuid.uuid4().hex[:8], "stage": "Idea", "next_step": "", "tagline": "", "notes": ""})
    items = store.pipeline()
    items.append(a)
    store.save_pipeline(items)
    return jsonify(a)


@app.post("/api/pipeline/import")
def import_apps():
    """One app per line: Name | one-liner | stage | next step"""
    text = str((request.get_json(force=True) or {}).get("text", ""))
    items = store.pipeline()
    added = 0
    for line in text.splitlines()[:100]:
        parts = [p.strip() for p in line.split("|")]
        if not parts or not parts[0]:
            continue
        stage = next((st for st in STAGES if len(parts) > 2 and st.lower() == parts[2].lower()), "Idea")
        items.append(clean_app(
            {"name": parts[0], "tagline": parts[1] if len(parts) > 1 else "",
             "stage": stage, "next_step": parts[3] if len(parts) > 3 else ""},
            {"id": uuid.uuid4().hex[:8], "stage": "Idea", "next_step": "", "tagline": "", "notes": ""}))
        added += 1
    store.save_pipeline(items)
    return jsonify(added=added)


@app.put("/api/pipeline/<app_id>")
def update_app(app_id):
    body = request.get_json(force=True) or {}
    items = store.pipeline()
    for i, a in enumerate(items):
        if a["id"] == app_id:
            items[i] = clean_app(body, a)
            store.save_pipeline(items)
            return jsonify(items[i])
    return jsonify(error="Not found"), 404


@app.delete("/api/pipeline/<app_id>")
def delete_app(app_id):
    items = [a for a in store.pipeline() if a["id"] != app_id]
    store.save_pipeline(items)
    return jsonify(ok=True)


# ---------- links ----------

@app.put("/api/links")
def save_links():
    body = request.get_json(force=True) or []
    links = []
    for l in body[:60]:
        label = str(l.get("label", "")).strip()[:60]
        url = str(l.get("url", "")).strip()[:500]
        if not label or not url:
            continue
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url
        links.append({
            "id": l.get("id") or uuid.uuid4().hex[:8],
            "label": label,
            "url": url,
            "group": str(l.get("group", "General")).strip()[:40] or "General",
        })
    store.save_links(links)
    return jsonify(links)


# ---------- settings ----------

@app.post("/api/settings")
def save_settings():
    body = request.get_json(force=True) or {}
    s = store.settings()
    if "anthropic_api_key" in body and body["anthropic_api_key"] != "":
        s["anthropic_api_key"] = str(body["anthropic_api_key"]).strip()
    if body.get("clear_api_key"):
        s["anthropic_api_key"] = ""
    if "ical_url" in body and body["ical_url"] != "":
        s["ical_url"] = str(body["ical_url"]).strip()
    if body.get("clear_ical_url"):
        s["ical_url"] = ""
    for field in ("model", "brief_time", "location_name", "owner_name", "company_name"):
        if field in body and str(body[field]).strip():
            s[field] = str(body[field]).strip()
    for field, n in (("brand_name", 24), ("brand_highlight", 3), ("brand_label", 16), ("brand_tagline", 60)):
        if field in body:
            s[field] = str(body[field]).strip()[:n]
    for field in ("color_primary", "color_highlight", "color_ink"):
        if field in body and HEX.match(str(body[field]).strip()):
            s[field] = str(body[field]).strip().lower()
    if body.get("reset_brand"):
        from store import DEFAULT_SETTINGS
        for k in ("brand_name", "brand_highlight", "brand_label", "brand_tagline",
                  "color_primary", "color_highlight", "color_ink"):
            s[k] = DEFAULT_SETTINGS[k]
    if "onboarded" in body:
        s["onboarded"] = bool(body["onboarded"])
    for field, lo, hi in (("monthly_call_cap", 0, 200), ("stall_days", 1, 365)):
        if field in body:
            try:
                s[field] = max(lo, min(hi, int(body[field])))
            except (TypeError, ValueError):
                pass
    for field in ("latitude", "longitude"):
        if field in body:
            try:
                s[field] = float(body[field]) if str(body[field]).strip() != "" else None
            except (TypeError, ValueError):
                pass
    store.save_settings(s)
    return jsonify(public_settings())


# ---------- brand ----------

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
LOGO_TYPES = {b"\x89PNG": ("png", "image/png"), b"\xff\xd8\xff": ("jpg", "image/jpeg"), b"RIFF": ("webp", "image/webp")}
BRAND_DIR = os.path.join(DATA_DIR, "brand")


def logo_path():
    for ext in ("png", "jpg", "webp"):
        p = os.path.join(BRAND_DIR, f"logo.{ext}")
        if os.path.exists(p):
            return p, ext
    return None


@app.get("/brand/logo")
def brand_logo():
    found = logo_path()
    if not found:
        return send_from_directory(app.static_folder, "mark.png", max_age=3600)
    path, ext = found
    mime = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}[ext]
    return send_file(path, mimetype=mime, max_age=3600)


@app.post("/api/brand/logo")
def upload_logo():
    """PNG, JPG, or WebP up to 1 MB. No SVG on purpose (it can carry scripts)."""
    data = request.get_data(cache=False)
    if not data or len(data) > 1_000_000:
        return jsonify(error="Pick an image under 1 MB"), 400
    kind = next((v for sig, v in LOGO_TYPES.items() if data.startswith(sig)), None)
    if kind is None or (kind[0] == "webp" and data[8:12] != b"WEBP"):
        return jsonify(error="Use a PNG, JPG, or WebP image"), 400
    os.makedirs(BRAND_DIR, exist_ok=True)
    for ext in ("png", "jpg", "webp"):
        try:
            os.remove(os.path.join(BRAND_DIR, f"logo.{ext}"))
        except FileNotFoundError:
            pass
    with open(os.path.join(BRAND_DIR, f"logo.{kind[0]}"), "wb") as f:
        f.write(data)
    s = store.settings(); s["logo_version"] = int(s.get("logo_version", 0)) + 1; store.save_settings(s)
    return jsonify(public_settings())


@app.delete("/api/brand/logo")
def delete_logo():
    for ext in ("png", "jpg", "webp"):
        try:
            os.remove(os.path.join(BRAND_DIR, f"logo.{ext}"))
        except FileNotFoundError:
            pass
    s = store.settings(); s["logo_version"] = int(s.get("logo_version", 0)) + 1; store.save_settings(s)
    return jsonify(public_settings())


# ---------- onboarding helpers ----------

@app.get("/api/geocode")
def geocode():
    """Look up a town so nobody has to type coordinates. Free, no key (Open-Meteo)."""
    q = request.args.get("q", "").strip()[:80]
    if not q:
        return jsonify(results=[])
    import requests
    try:
        r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": q.split(",")[0], "count": 6, "language": "en"}, timeout=10)
        r.raise_for_status()
        out = []
        for g in r.json().get("results", []) or []:
            label = ", ".join(x for x in (g.get("name"), g.get("admin1"), g.get("country_code")) if x)
            out.append({"label": label, "latitude": g["latitude"], "longitude": g["longitude"]})
        hint = q.split(",")[1].strip().lower() if "," in q else ""
        if hint:  # "Springfield, MO" -> float matching state/region first
            out.sort(key=lambda o: hint not in o["label"].lower())
        return jsonify(results=out)
    except Exception as e:
        return jsonify(results=[], error=f"lookup unavailable ({type(e).__name__})")


# ---------- brief ----------

@app.post("/api/brief/regenerate")
def regenerate():
    b = brief_mod.generate(store, now_local())
    return jsonify(b)


def scheduler():
    """Generate today's brief once, at or after the configured time."""
    while True:
        try:
            now = now_local()
            hh, mm = (store.settings().get("brief_time") or "06:00").split(":")
            due = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            if now >= due and not store.brief(now.date().isoformat()):
                brief_mod.generate(store, now)
        except Exception as e:  # never let the loop die
            print("scheduler error:", e, flush=True)
        time.sleep(60)


if os.environ.get("DISABLE_SCHEDULER") != "1":
    threading.Thread(target=scheduler, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
