"""Handles repository_dispatch events sent by the Apple Home shortcut (rooms) and the dashboard (meter readings).
Payload arrives as JSON in the PAYLOAD env variable."""
import os, sys, json, datetime as dt
import crypto_util as cu

PASS = os.environ["DATA_PASSPHRASE"]
event = os.environ.get("EVENT_TYPE", "")
payload = json.loads(os.environ.get("PAYLOAD") or "{}")
DATA = os.path.join(os.path.dirname(__file__), "..", "data")
P = lambda n: os.path.normpath(os.path.join(DATA, n))
now_iso = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

def num(x):
    """Shortcuts sends '23,22 °C' or '63,39' as text; turn it into a float."""
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace("°C", "").replace("%", "").strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None

if event == "rooms":
    rooms = cu.load(P("rooms.enc"), PASS, {"latest": {}, "history": []})
    sample = {"t": now_iso, "r": {}}
    for name, vals in payload.items():
        if not isinstance(vals, dict):
            continue
        t, h = num(vals.get("t")), num(vals.get("h"))
        if t is None and h is None:
            continue
        rooms["latest"][name] = {"t": t, "h": h, "updated": now_iso}
        sample["r"][name] = [t, h]
    rooms["history"].append(sample)
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=60)).isoformat()
    rooms["history"] = [s for s in rooms["history"] if s["t"] >= cutoff]
    cu.save(P("rooms.enc"), PASS, rooms)
    print("rooms:", list(sample["r"].keys()))

elif event == "meter":
    meters = cu.load(P("meters.enc"), PASS, {"readings": []})
    entry = {"t": payload.get("date") or now_iso[:10],
             "household": num(payload.get("household")), "heatpump": num(payload.get("heatpump")),
             "export": num(payload.get("export")), "note": payload.get("note", "")}
    meters["readings"].append(entry)
    meters["readings"].sort(key=lambda e: e["t"])
    cu.save(P("meters.enc"), PASS, meters)
    print("meter reading stored:", entry)
else:
    sys.exit(f"unknown event type {event!r}")
