# Hausenergie

Dein PV Dashboard: Fox ESS (Wechselrichter, Batterie), Daikin Altherma (Wärmepumpe) und die Timmerflotte Raumsensoren aus Apple Home, gesammelt in diesem Repository, angezeigt auf deinem gerenderten Haus.

Kosten: 0 €. Keine Hardware zu Hause. Alle Daten im Repository sind verschlüsselt, das Dashboard entschlüsselt sie im Browser mit deiner Passphrase.

## Wie es funktioniert

```
alle 10 Min   GitHub Actions  ──► Fox ESS Cloud API      ─┐
                                ──► Daikin Onecta API      ─┤─► data/*.enc (verschlüsselt) ─► GitHub Pages ─► Dashboard
alle 2 Std    Apple TV Kurzbefehl ─► GitHub (Sensordaten) ─┘
manuell       Dashboard ─► GitHub (Zählerstände, "Jetzt aktualisieren")
```

## Einrichtung, Schritt für Schritt

### 1. GitHub Konto und Repository

1. Konto anlegen auf github.com (kostenlos).
2. Oben rechts Plus, "New repository". Name `hausenergie`, **Public** (GitHub Pages ist im kostenlosen Plan nur für öffentliche Repositories, deshalb die Verschlüsselung), Haken bei "Add a README" weglassen. "Create repository".
3. Auf der leeren Repo Seite "uploading an existing file" anklicken, den gesamten Inhalt dieses Ordners hineinziehen (inklusive der Ordner `.github`, `scripts`, `assets`, `data`). Falls dein Browser den versteckten Ordner `.github` nicht mitnimmt: im Finder Cmd Shift Punkt drücken, dann ist er sichtbar. Unten "Commit changes".

### 2. Passphrase und Secrets

Im Repository: Settings, Secrets and variables, Actions, "New repository secret". Vier Einträge:

| Name | Wert |
|---|---|
| `DATA_PASSPHRASE` | Ein langes Passwort deiner Wahl (z. B. 4 Wörter). Dasselbe trägst du später im Dashboard ein. |
| `FOX_API_KEY` | Der API Key aus der FoxESS Cloud (App: Ich, OpenPlatform, API Management, Generate). |
| `DAIKIN_CLIENT_ID` | Aus dem Daikin Developer Portal, sobald das Ticket gelöst ist. Vorerst weglassen. |
| `DAIKIN_CLIENT_SECRET` | Ebenfalls Daikin. Vorerst weglassen. |

Optional `FOX_DEVICE_SN`, falls du mehrere Fox Geräte hast. Sonst nimmt das Skript das erste.

### 3. Workflow starten

Tab "Actions". Beim ersten Mal auf "I understand my workflows, go ahead and enable them". Dann links "Daten sammeln", rechts "Run workflow", "Run workflow". Nach etwa einer Minute liegt im Ordner `data` die erste `latest.enc`. Ab jetzt läuft es alle 10 Minuten von selbst.

### 4. GitHub Pages einschalten

Settings, Pages, unter "Build and deployment" Source "Deploy from a branch", Branch `main`, Ordner `/ (root)`, Save. Nach ein bis zwei Minuten ist das Dashboard erreichbar unter

`https://DEINNAME.github.io/hausenergie/`

Auf dem iPhone in Safari öffnen, Teilen, "Zum Home Bildschirm". Beim ersten Öffnen die Passphrase eintragen (Einstellungen). Sie bleibt nur auf dem Gerät.

### 5. GitHub Token für das Dashboard (optional, empfohlen)

Damit der Knopf "Jetzt aktualisieren" und das Eintragen von Zählerständen aus dem Dashboard funktionieren, braucht die Seite ein Token:

1. GitHub, Profilbild, Settings, Developer settings, Personal access tokens, Fine grained tokens, "Generate new token".
2. Name `hausenergie-app`, Ablauf 1 Jahr, Repository access "Only select repositories", `hausenergie` wählen.
3. Permissions: Repository permissions, **Actions: Read and write**, **Contents: Read and write**. Generate, Token kopieren.
4. Im Dashboard unter Einstellungen bei "GitHub Token" einfügen. Dasselbe Token nutzt auch der Apple TV Kurzbefehl (Schritt 7).

### 6. Daikin verbinden (sobald Client ID und Secret da sind)

1. Beide als Secrets eintragen (Schritt 2). Im Developer Portal muss die Redirect URI der App `https://localhost/callback` sein.
2. Diese Adresse im Browser öffnen, `CLIENT_ID` ersetzen:

   `https://idp.onecta.daikineurope.com/v1/oidc/authorize?response_type=code&client_id=CLIENT_ID&redirect_uri=https://localhost/callback&scope=openid%20onecta:basic.integration%20offline_access`

3. Mit dem Onecta Konto anmelden, Zugriff erlauben. Der Browser landet auf einer Fehlerseite (localhost gibt es nicht), das ist richtig so. In der Adresszeile steht `...callback?code=XXXX`. Alles hinter `code=` kopieren.
4. Repository, Actions, "Daikin verbinden", "Run workflow", den Code einfügen, starten. Fertig, ab dem nächsten Lauf sind die Wärmepumpendaten dabei. Der Daikin Refresh Token rotiert bei jedem Abruf und wird verschlüsselt in `data/daikin_token.enc` mitgeführt.

Daikin erlaubt 200 Abrufe pro Tag. Der 10 Minuten Takt braucht 144, der Rest ist Reserve für "Jetzt aktualisieren".

### 7. Raumsensoren aus Apple Home

Der Kurzbefehl aus dem Test wird erweitert. Er läuft als Automation auf dem Apple TV und schickt alle Räume auf einmal.

**Aufbau des Kurzbefehls:**

1. Pro Sensor ein Block "Status von Zuhause abrufen" für die Temperatur und einer für die Luftfeuchtigkeit, jeweils gefolgt von "Variable festlegen" mit Namen wie `Küche_T` und `Küche_H`.
2. Aktion "Wörterbuch". Für jeden Raum einen Eintrag vom Typ Wörterbuch mit dem Raumnamen als Schlüssel (`Küche`), darin zwei Texteinträge: `t` mit der Variable `Küche_T`, `h` mit `Küche_H`. Einheiten und Kommas im Text sind in Ordnung, das Skript bereinigt sie.
3. Aktion "Wörterbuch" (noch eins): `event_type` = `rooms`, `client_payload` = das Wörterbuch aus Schritt 2.
4. Aktion "Inhalte von URL abrufen":
   - URL: `https://api.github.com/repos/DEINNAME/hausenergie/dispatches`
   - Methode POST
   - Header: `Authorization` = `Bearer DEIN_TOKEN`, `Accept` = `application/vnd.github+json`
   - Haupttext anfordern: JSON, als Inhalt das Wörterbuch aus Schritt 3.
5. Einmal per Play testen (beim ersten Mal "Immer erlauben" für api.github.com). Im Repository unter Actions erscheint ein Lauf "Daten sammeln", danach die Räume im Dashboard.

**Zeitsteuerung:** Home App, Automation, "Eine Tageszeit tritt ein", zum Beispiel 6, 9, 12, 15, 18, 21 Uhr (je eine Automation oder, wo möglich, eine mit mehreren Zeiten), jeweils "In Kurzbefehl umwandeln" und den fertigen Kurzbefehl per "Kurzbefehl ausführen" aufrufen. Wichtig: Diese Automationen laufen auf dem Home Hub, das iPhone muss nicht zu Hause sein.

### 8. Zählerstände

Tab "Zähler" im Dashboard. Die App rechnet die Zähler zwischen deinen Ablesungen virtuell weiter (Fox Tageswerte für Bezug und Einspeisung, Daikin Verbrauch für den Wärmepumpenzähler) und zeigt bei jeder neuen Ablesung, wie gut die Schätzung war.

## Dateien

| Pfad | Zweck |
|---|---|
| `index.html` | Das Dashboard |
| `assets/house_*.png` | Deine vier Blender Renderings |
| `scripts/collect.py` | Holt Fox und Daikin, schreibt `data/latest.enc`, `history.enc` (14 Tage, 10 Minuten Takt), `daily.enc` (Tageswerte) |
| `scripts/ingest_dispatch.py` | Nimmt Sensordaten und Zählerstände entgegen (`rooms.enc`, `meters.enc`) |
| `scripts/daikin_auth.py` | Einmalige Daikin Freigabe |
| `scripts/crypto_util.py` | AES GCM Verschlüsselung, identisch im Browser nachgebaut |
| `.github/workflows/collect.yml` | Zeitplan, manueller Start, Sensor und Zähler Events |
| `.github/workflows/daikin_auth.yml` | Workflow "Daikin verbinden" |

## Hinweise

- GitHub führt Zeitpläne nicht sekundengenau aus, einige Minuten Verzug sind normal. Für dieses Dashboard egal.
- Ein öffentliches Repository zeigt Code und Renderings, aber keine Messwerte: alle `data/*.enc` Dateien sind ohne Passphrase unlesbar. Wer die Passphrase hat, kann sie lesen, also behandle sie wie ein Passwort.
- Wenn du das Repository lieber privat hättest, geht das mit GitHub Pro (etwa 4 € im Monat), dann funktioniert Pages auch privat. Nichts weiter muss sich ändern.
- Fehler beim Abruf stehen im Dashboard oben als gelber Hinweis und im Actions Log.
