"""Hausenergie collector: pulls Fox ESS and Daikin Onecta data, stores encrypted JSON in data/.
Runs in GitHub Actions every 10 minutes. Missing credentials are skipped, not fatal."""
import os, sys, time, json, hashlib, datetime as dt
import requests
import crypto_util as cu

PASS = os.environ.get("DATA_PASSPHRASE")
if not PASS:
    sys.exit("DATA_PASSPHRASE secret missing")

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
P = lambda name: os.path.normpath(os.path.join(DATA, name))
now = dt.datetime.now(dt.timezone.utc)
now_iso = now.replace(microsecond=0).isoformat()

latest = cu.load(P("latest.enc"), PASS, {})
history = cu.load(P("history.enc"), PASS, [])        # 10-minute samples, last 14 days
daily = cu.load(P("daily.enc"), PASS, {})            # date -> fox daily totals (kWh)
latest["updated"] = now_iso

# ------------------------------------------------------------------ Fox ESS
FOX_KEY = os.environ.get("FOX_API_KEY")
FOX_BASE = "https://www.foxesscloud.com"
FOX_VARS = ["pvPower", "loadsPower", "feedinPower", "gridConsumptionPower",
            "batChargePower", "batDischargePower", "SoC", "generationPower", "invTemperation"]
FOX_REPORT = ["generation", "feedin", "gridConsumption", "chargeEnergyToTal", "dischargeEnergyToTal", "loads"]

def fox(path, body):
    ts = str(int(time.time() * 1000))
    # Fox signs with the literal characters backslash r backslash n, not a real line break
    sig = hashlib.md5((path + r"\r\n" + FOX_KEY + r"\r\n" + ts).encode()).hexdigest()
    h = {"token": FOX_KEY, "timestamp": ts, "signature": sig, "lang": "en",
         "Content-Type": "application/json", "User-Agent": "hausenergie/1.0"}
    r = requests.post(FOX_BASE + path, headers=h, json=body, timeout=30)
    r.raise_for_status()
    j = r.json()
    if j.get("errno") != 0:
        raise RuntimeError(f"Fox {path}: errno {j.get('errno')} {j.get('msg')}")
    return j["result"]

def collect_fox():
    sn = os.environ.get("FOX_DEVICE_SN")
    if not sn:
        devs = fox("/op/v0/device/list", {"currentPage": 1, "pageSize": 10})
        sn = devs["data"][0]["deviceSN"]
    real = fox("/op/v0/device/real/query", {"sn": sn, "variables": FOX_VARS})
    vals = {d["variable"]: d.get("value") for d in real[0]["datas"]}
    fox_now = {
        "sn": sn,
        "pv_kw": vals.get("pvPower"),
        "load_kw": vals.get("loadsPower"),
        "feedin_kw": vals.get("feedinPower"),
        "grid_kw": vals.get("gridConsumptionPower"),
        "bat_charge_kw": vals.get("batChargePower"),
        "bat_discharge_kw": vals.get("batDischargePower"),
        "soc": vals.get("SoC"),
        "inv_temp": vals.get("invTemperation"),
    }
    latest["fox"] = fox_now
    history.append({"t": now_iso, **{k: fox_now[k] for k in
                   ("pv_kw", "load_kw", "feedin_kw", "grid_kw", "bat_charge_kw", "bat_discharge_kw", "soc")}})
    # daily totals for this month (and last month during the first days)
    months = [(now.year, now.month)]
    if now.day <= 3:
        prev = (now.replace(day=1) - dt.timedelta(days=1))
        months.append((prev.year, prev.month))
    for (y, m) in months:
        rep = fox("/op/v0/device/report/query",
                  {"sn": sn, "year": y, "month": m, "dimension": "month", "variables": FOX_REPORT})
        for series in rep:
            for i, v in enumerate(series.get("values") or []):
                date = f"{y:04d}-{m:02d}-{i+1:02d}"
                try:
                    dt.date.fromisoformat(date)
                except ValueError:
                    continue
                daily.setdefault(date, {})[series["variable"]] = v

# ------------------------------------------------------------------ Daikin Onecta
D_ID, D_SECRET = os.environ.get("DAIKIN_CLIENT_ID"), os.environ.get("DAIKIN_CLIENT_SECRET")
IDP = "https://idp.onecta.daikineurope.com/v1/oidc"

def collect_daikin():
    tok = cu.load(P("daikin_token.enc"), PASS, {})
    if not tok.get("refresh_token"):
        print("Daikin: no refresh token yet, run the 'Daikin verbinden' workflow first")
        return
    r = requests.post(f"{IDP}/token", data={"grant_type": "refresh_token", "client_id": D_ID,
                      "client_secret": D_SECRET, "refresh_token": tok["refresh_token"]}, timeout=30)
    r.raise_for_status()
    t = r.json()
    # refresh tokens rotate on every use, so persist the new one immediately
    cu.save(P("daikin_token.enc"), PASS, {"refresh_token": t["refresh_token"], "updated": now_iso})
    h = {"Authorization": f"Bearer {t['access_token']}", "Accept-Encoding": "gzip"}
    g = requests.get("https://api.onecta.daikineurope.com/v1/gateway-devices", headers=h, timeout=30)
    g.raise_for_status()
    latest["daikin_quota"] = {k: g.headers.get(k) for k in ("X-RateLimit-Remaining-day", "X-RateLimit-Remaining-minute")}
    out = []
    for dev in g.json():
        d = {"id": dev.get("id"), "online": (dev.get("isCloudConnectionUp") or {}).get("value"), "points": {}}
        for mp in dev.get("managementPoints", []):
            typ = mp.get("managementPointType")
            if typ not in ("climateControl", "domesticHotWaterTank", "domesticHotWaterFlowThrough", "gateway", "outdoorUnit"):
                continue
            def v(key, *path):
                cur = mp.get(key, {}).get("value")
                for p in path:
                    cur = (cur or {}).get(p) if isinstance(cur, dict) else None
                return cur.get("value") if isinstance(cur, dict) and "value" in cur else cur
            point = {
                "on": v("onOffMode"), "mode": v("operationMode"), "error": v("errorCode"),
                "in_error": v("isInErrorState"), "control_mode": v("controlMode"),
                "room_temp": v("sensoryData", "roomTemperature"),
                "outdoor_temp": v("sensoryData", "outdoorTemperature"),
                "leaving_water_temp": v("sensoryData", "leavingWaterTemperature"),
                "tank_temp": v("sensoryData", "tankTemperature"),
                "consumption": (mp.get("consumptionData", {}).get("value") or {}).get("electrical"),
                "model": v("modelInfo"),
            }
            d["points"][typ] = {k: val for k, val in point.items() if val is not None}
        out.append(d)
        # daily electrical kWh from Daikin's 2 hour bins (d = yesterday + today, 24 bins)
        today, yday = now.date().isoformat(), (now.date() - dt.timedelta(days=1)).isoformat()
        for typ, key in (("climateControl", "hp_heating"), ("domesticHotWaterTank", "hp_dhw"), ("domesticHotWaterFlowThrough", "hp_dhw")):
            c = ((d["points"].get(typ) or {}).get("consumption") or {}).get("heating", {})
            bins = c.get("d") or []
            if len(bins) == 24:
                num = lambda xs: round(sum(x for x in xs if isinstance(x, (int, float))), 2)
                daily.setdefault(yday, {})[key] = num(bins[:12])
                daily.setdefault(today, {})[key] = num(bins[12:])
    latest["daikin"] = out

errors = []
if FOX_KEY:
    try:
        collect_fox()
    except Exception as e:
        errors.append(f"Fox: {e}"); print(errors[-1])
else:
    print("Fox: FOX_API_KEY not set, skipping")
if D_ID and D_SECRET:
    try:
        collect_daikin()
    except Exception as e:
        errors.append(f"Daikin: {e}"); print(errors[-1])
else:
    print("Daikin: credentials not set, skipping")

latest["errors"] = errors
cutoff = (now - dt.timedelta(days=14)).isoformat()
history = [h for h in history if h["t"] >= cutoff]
cu.save(P("latest.enc"), PASS, latest)
cu.save(P("history.enc"), PASS, history)
cu.save(P("daily.enc"), PASS, daily)
print("ok", now_iso, "errors:", errors)
