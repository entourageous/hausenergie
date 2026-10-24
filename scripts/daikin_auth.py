"""One-time Daikin authorisation. Exchanges the authorization code (from the redirect URL)
for a refresh token and stores it encrypted. Triggered via the 'Daikin verbinden' workflow."""
import os, sys, datetime as dt
import requests
import crypto_util as cu

code = os.environ.get("AUTH_CODE", "").strip()
redirect = os.environ.get("DAIKIN_REDIRECT_URI", "https://localhost/callback")
cid, sec, PASS = os.environ["DAIKIN_CLIENT_ID"], os.environ["DAIKIN_CLIENT_SECRET"], os.environ["DATA_PASSPHRASE"]
if not code:
    sys.exit("AUTH_CODE missing")
r = requests.post("https://idp.onecta.daikineurope.com/v1/oidc/token",
                  data={"grant_type": "authorization_code", "client_id": cid, "client_secret": sec,
                        "code": code, "redirect_uri": redirect}, timeout=30)
print("status", r.status_code)
if r.status_code != 200:
    sys.exit(r.text)
tok = r.json()
path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "daikin_token.enc"))
cu.save(path, PASS, {"refresh_token": tok["refresh_token"],
                     "updated": dt.datetime.now(dt.timezone.utc).isoformat()})
print("Daikin verbunden, Refresh Token gespeichert.")
