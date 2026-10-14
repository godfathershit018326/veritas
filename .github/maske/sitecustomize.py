import csv
import json
import os
import re
import sys


def _kuerzel():
    menge = set()
    for datei in ("finviz_3.csv", "darvas.csv", "dritte_liste.csv", "vierte_liste.csv", "einzelaktien.csv",
                  "auto_wachstum.csv"):
        try:
            with open(datei, encoding="utf-8-sig") as f:
                for z in csv.DictReader(f):
                    t = (z.get("Ticker") or z.get("ticker") or "").strip().upper()
                    if t:
                        menge.add(t)
        except Exception:  # noqa: BLE001
            pass
    for datei in ("positionen.json", "alarm_kaufpunkte.json", "fokusliste.json"):
        try:
            with open(datei, encoding="utf-8") as f:
                d = json.load(f)
            schluessel = d.get("aktien", d) if isinstance(d, dict) else {}
            if isinstance(schluessel, dict):
                menge |= {str(k).split("|")[0].upper() for k in schluessel}
            elif isinstance(schluessel, list):
                menge |= {str(x.get("ticker", x) if isinstance(x, dict) else x).split("|")[0].upper() for x in schluessel}
        except Exception:  # noqa: BLE001
            pass
    for pfad in (os.path.join(os.environ.get("DATEN_EINSTELLUNGEN", ".daten"), "blacklist", "blacklist.json"),
                 "blacklist.json"):
        try:
            with open(pfad, encoding="utf-8") as f:
                menge |= {str(e.get("ticker", "")).split("|")[0].upper() for e in json.load(f).get("eintraege", [])}
        except Exception:  # noqa: BLE001
            pass
    menge |= {t.strip().upper() for t in os.environ.get("VERITAS_MASKE_EXTRA", "").split(",")}
    return {t for t in menge if re.fullmatch(r"[A-Z0-9.\-]{1,10}", t or "")}


class _Maske:
    def __init__(self, strom, muster):
        self._strom, self._muster = strom, muster

    def write(self, text):
        try:
            if isinstance(text, str):
                text = self._muster.sub("•••", text)
        except Exception:  # noqa: BLE001
            pass
        return self._strom.write(text)

    def __getattr__(self, name):
        return getattr(self._strom, name)


def _einschalten():
    if os.environ.get("VERITAS_MASKE") == "aus":
        return
    k = _kuerzel()
    if not k:
        return
    teile = sorted((re.escape(t) for t in k), key=len, reverse=True)
    muster = re.compile(r"(?<![A-Za-z0-9.\-])(?:" + "|".join(teile) + r")(?![A-Za-z0-9\-]|\.[A-Za-z0-9])")
    sys.stdout = _Maske(sys.stdout, muster)
    sys.stderr = _Maske(sys.stderr, muster)


try:
    _einschalten()
except Exception:  # noqa: BLE001
    pass
