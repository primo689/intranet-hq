"""Tiny JSON file store. One process, one lock, atomic writes."""
import json
import os
import tempfile
import threading
from datetime import datetime

LOCK = threading.RLock()

DEFAULT_SETTINGS = {
    "anthropic_api_key": "",
    "ical_url": "",
    "model": "claude-haiku-5-5",
    "brief_time": "06:00",
    "timezone": "America/Chicago",
    "monthly_call_cap": 40,  # hard stop: at most this many Claude calls per month
    "stall_days": 14,        # an app untouched this long gets a nudge
    "onboarded": False,     # first-run setup done
    "owner_name": "",       # used in the greeting and the brief
    "company_name": "Paragdise Ventures LLC",
    # look and feel (defaults are the Paragdise brand)
    "brand_name": "PARAGDISE",
    "brand_highlight": "G",       # first matching letter shows in the highlight color
    "brand_label": "HQ",
    "brand_tagline": "Build something better.",
    "color_primary": "#006a7a",
    "color_highlight": "#f4c430",
    "color_ink": "#0b2d3a",
    "logo_version": 0,
    "location_name": "",    # weather is skipped until a location is set
    "latitude": None,
    "longitude": None,
}

LINKS = [
    ("Apps", "App Store Connect", "https://appstoreconnect.apple.com"),
    ("Apps", "Apple Developer", "https://developer.apple.com/account"),
    ("Apps", "TestFlight", "https://appstoreconnect.apple.com/apps"),
    ("Web", "paragdise.com", "https://paragdise.com"),
    ("Web", "cPanel", "https://paragdise.com/cpanel"),
    ("Web", "Namecheap", "https://ap.www.namecheap.com/domains/list"),
    ("Web", "Private Email", "https://privateemail.com"),
    ("Media", "YouTube Studio", "https://studio.youtube.com"),
    ("Book", "Amazon KDP", "https://kdp.amazon.com"),
    ("Docs", "BookStack", "http://umbrel.local:6875"),
]


class Store:
    def __init__(self, root):
        self.root = root
        os.makedirs(os.path.join(root, "briefs"), exist_ok=True)
        if not os.path.exists(self._p("pipeline.json")):
            self._write("pipeline.json", [])
        if not os.path.exists(self._p("links.json")):
            self._write("links.json", [
                {"id": f"l{i}", "group": g, "label": l, "url": u}
                for i, (g, l, u) in enumerate(LINKS)
            ])

    def _p(self, name):
        return os.path.join(self.root, name)

    def _read(self, name, default):
        with LOCK:
            try:
                with open(self._p(name)) as f:
                    return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return default

    def _write(self, name, data):
        with LOCK:
            path = self._p(name)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, path)

    # pipeline / links
    def pipeline(self):
        return self._read("pipeline.json", [])

    def save_pipeline(self, items):
        self._write("pipeline.json", items)

    def links(self):
        return self._read("links.json", [])

    def save_links(self, links):
        self._write("links.json", links)

    # settings
    def settings(self):
        s = dict(DEFAULT_SETTINGS)
        s.update(self._read("settings.json", {}))
        return s

    def save_settings(self, s):
        self._write("settings.json", s)

    # usage
    def usage(self, month):
        u = self._read("usage.json", {})
        cap = self.settings().get("monthly_call_cap", 40)
        if u.get("month") != month:
            u = {"month": month, "calls": 0, "input_tokens": 0, "output_tokens": 0}
        u["cap"] = cap
        return u

    def record_usage(self, month, input_tokens, output_tokens):
        with LOCK:
            u = self.usage(month)
            u["calls"] += 1
            u["input_tokens"] += int(input_tokens or 0)
            u["output_tokens"] += int(output_tokens or 0)
            u.pop("cap", None)
            self._write("usage.json", u)

    # briefs
    def brief(self, day):
        return self._read(os.path.join("briefs", f"{day}.json"), None)

    def save_brief(self, day, b):
        self._write(os.path.join("briefs", f"{day}.json"), b)

    def latest_brief(self):
        with LOCK:
            files = sorted(f for f in os.listdir(self._p("briefs")) if f.endswith(".json"))
        return self._read(os.path.join("briefs", files[-1]), None) if files else None
