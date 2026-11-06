"""Daily brief: gather facts cheaply on the server, let Claude write only the summary.

Cost controls:
  * one call per day (cached to disk; opening the page is free)
  * smallest model by default (Haiku), max_tokens capped
  * hard monthly call cap; past it, a plain brief is written without Claude
"""
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import json

import requests

TZ_NAME = "America/Chicago"

WMO = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle", 61: "light rain", 63: "rain",
    65: "heavy rain", 66: "freezing rain", 67: "freezing rain", 71: "light snow",
    73: "snow", 75: "heavy snow", 77: "snow grains", 80: "rain showers",
    81: "rain showers", 82: "heavy showers", 85: "snow showers", 86: "snow showers",
    95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail",
}

SYSTEM = (
    "You write {owner}'s morning brief for {company}. "
    "Voice: casual, plain, direct, warm, human. Short sentences. "
    "Never use em dashes. No hype, no bragging, no motivational or reward language. "
    "Use only the facts provided. Never invent events, numbers, or details. "
    "Format: one short opening line, then 2 to 4 lines that each start with '- '. "
    "Cover what matters on the calendar, weather only if it affects the day, "
    "and the one or two pipeline items most worth attention today. "
    "If the calendar is empty, say it's an open day. Stay under 110 words."
)


def tz():
    return ZoneInfo(TZ_NAME)


def get_weather(s):
    if s.get("latitude") is None or s.get("longitude") is None:
        return {"error": "no location set"}
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": s["latitude"], "longitude": s["longitude"],
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                "current": "temperature_2m,weather_code",
                "temperature_unit": "fahrenheit", "timezone": TZ_NAME, "forecast_days": 1,
            },
            timeout=10,
        )
        r.raise_for_status()
        d = r.json()
        daily = d["daily"]
        return {
            "location": s.get("location_name", ""),
            "now_f": round(d["current"]["temperature_2m"]),
            "high_f": round(daily["temperature_2m_max"][0]),
            "low_f": round(daily["temperature_2m_min"][0]),
            "rain_chance": daily["precipitation_probability_max"][0],
            "conditions": WMO.get(daily["weather_code"][0], "mixed"),
        }
    except Exception as e:
        return {"error": f"weather unavailable ({type(e).__name__})"}


def get_calendar(s, day):
    url = s.get("ical_url")
    if not url:
        return {"error": "no calendar connected"}
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    try:
        import icalendar
        import recurring_ical_events
        r = requests.get(url, timeout=15)
        if r.status_code in (401, 403, 404):
            return {"error": f"Google refused the calendar link ({r.status_code}). Use the Secret address in iCal format, and make sure you copied all of it."}
        r.raise_for_status()
        cal = icalendar.Calendar.from_ical(r.content)
        events = []
        for ev in recurring_ical_events.of(cal).at(day):
            start = ev.get("DTSTART").dt
            end = ev.get("DTEND").dt if ev.get("DTEND") else None
            all_day = not isinstance(start, datetime)
            if not all_day:
                start = start.astimezone(tz())
                end = end.astimezone(tz()) if isinstance(end, datetime) else None
            events.append({
                "title": str(ev.get("SUMMARY", "Busy")),
                "all_day": all_day,
                "start": "" if all_day else start.strftime("%-I:%M %p"),
                "end": "" if (all_day or not end) else end.strftime("%-I:%M %p"),
                "location": str(ev.get("LOCATION", "") or ""),
                "_sort": "" if all_day else start.strftime("%H%M"),
            })
        events.sort(key=lambda e: e["_sort"])
        for e in events:
            e.pop("_sort")
        return {"events": events[:15]}
    except requests.HTTPError as e:
        return {"error": f"calendar unavailable (HTTP {e.response.status_code if e.response is not None else '?'})"}
    except ValueError:
        return {"error": "That link didn't return a calendar file. Use the Secret address in iCal format (it ends in .ics)."}
    except Exception as e:
        return {"error": f"calendar unavailable ({type(e).__name__})"}


def get_nudges(pipeline, stall_days, now):
    nudges = []
    for a in pipeline:
        if a.get("stage") == "Live":
            continue
        try:
            updated = datetime.fromisoformat(a["updated"])
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=tz())
            days = (now - updated).days
        except Exception:
            days = 0
        active = a.get("stage") in ("Building", "Testing", "Submitted")
        if active or days >= stall_days:
            nudges.append({
                "app": a["name"], "stage": a["stage"],
                "next_step": a.get("next_step") or "(no next step set)",
                "days_since_update": days,
                "stalled": days >= stall_days,
            })
    # active work first, then longest-stalled
    order = {"Submitted": 0, "Testing": 1, "Building": 2, "Idea": 3}
    nudges.sort(key=lambda n: (order.get(n["stage"], 9), -n["days_since_update"]))
    return nudges[:5]


def plain_brief(facts):
    lines = [f"Here's {facts['weekday']}."]
    ev = facts["calendar"].get("events")
    if ev:
        timed = [e for e in ev if not e["all_day"]]
        first = timed[0] if timed else ev[0]
        when = "all day" if first["all_day"] else first["start"]
        more = f", plus {len(ev) - 1} more" if len(ev) > 1 else ""
        lines.append(f"- First up: {first['title']} ({when}){more}.")
    elif ev == []:
        lines.append("- Calendar is open today.")
    w = facts["weather"]
    if "high_f" in w:
        lines.append(f"- {w['conditions'].capitalize()}, high {w['high_f']}, low {w['low_f']}, {w['rain_chance']}% chance of rain.")
    for n in facts["nudges"][:2]:
        lines.append(f"- {n['app']} ({n['stage']}): {n['next_step']}")
    return "\n".join(lines)


def strip_dashes(text):
    return text.replace(" — ", ", ").replace("—", ", ").replace("–", "-")


def generate(store, now):
    s = store.settings()
    day = now.date()
    month = now.strftime("%Y-%m")
    facts = {
        "date": day.isoformat(),
        "weekday": now.strftime("%A, %B %-d"),
        "weather": get_weather(s),
        "calendar": get_calendar(s, day),
        "nudges": get_nudges(store.pipeline(), int(s.get("stall_days", 14)), now),
    }

    usage = store.usage(month)
    text, source, note = None, "plain", ""
    if not s.get("anthropic_api_key"):
        note = "No API key set, so this is the plain version."
    elif usage["calls"] >= int(s.get("monthly_call_cap", 40)):
        note = "Monthly Claude cap reached, so this is the plain version."
    else:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=s["anthropic_api_key"])
            resp = client.messages.create(
                model=s.get("model") or "claude-haiku-5-5",
                max_tokens=300,
                system=SYSTEM.format(owner=s.get("owner_name") or "the owner",
                                     company=s.get("company_name") or "the company"),
                messages=[{"role": "user", "content": "Facts for today (JSON):\n" + json.dumps(facts)}],
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
            store.record_usage(month, resp.usage.input_tokens, resp.usage.output_tokens)
            source = "claude"
        except Exception as e:
            note = f"Claude call failed ({type(e).__name__}), so this is the plain version."
            text = None

    if not text:
        text = plain_brief(facts)

    b = {
        "date": day.isoformat(),
        "generated_at": now.isoformat(timespec="seconds"),
        "source": source,
        "note": note,
        "text": strip_dashes(text),
        "facts": facts,
    }
    store.save_brief(day.isoformat(), b)
    return b
