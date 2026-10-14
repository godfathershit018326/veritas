import csv
import json
import os
import re
import sys
import threading

_LISTEN = ("finviz_3.csv", "darvas.csv", "dritte_liste.csv", "vierte_liste.csv", "einzelaktien.csv",
           "auto_wachstum.csv", "episodic_kandidaten.csv", "hoch52_zahlen_kandidaten.csv")
_JSONS = ("positionen.json", "alarm_kaufpunkte.json", "fokusliste.json")
_STOPP = {"OK", "ID", "IO", "ON", "IT", "AN", "AM", "UM", "IN", "AT", "BE", "DE", "API", "CSV", "UTC", "USA", "USD",
          "EUR", "SPY", "QQQ", "IWM", "DIA", "EMA", "SMA", "RS", "IPO", "ALL", "AND", "THE", "FOR", "ARE", "ONE", "NEW"}
_FORM = re.compile(r"(?:,?\s+(?:Inc\.?|Incorporated|Corp\.?|Corporation|Co\.?|Company|Ltd\.?|Limited|plc|PLC|"
                   r"N\.?V\.?|S\.?A\.?|AG|SE|LLC|L\.?P\.?|LP|Holdings?|Group|Trust|ADR|Class [A-C]|Common Stock|"
                   r"Ordinary Shares|American Depositary Shares?))+\.?\s*$")


def _kern(firma):
    f = (firma or "").strip().strip('"')
    if " - " in f:
        f = f.split(" - ")[0]
    alt = None
    while alt != f:
        alt = f
        f = _FORM.sub("", f).strip().rstrip(",").strip()
    return f[4:] if f.lower().startswith("the ") else f


def _laden():
    kuerzel, namen = set(), set()
    for datei in _LISTEN:
        try:
            with open(datei, encoding="utf-8-sig") as f:
                for z in csv.DictReader(f):
                    t = (z.get("Ticker") or z.get("ticker") or "").strip().upper()
                    if t:
                        kuerzel.add(t)
                    n = _kern(z.get("Company") or z.get("Firma") or "")
                    if len(n) >= 5:
                        namen.add(n)
        except Exception:
            pass
    for datei in _JSONS:
        try:
            with open(datei, encoding="utf-8") as f:
                d = json.load(f)
            werte = d.get("aktien", d) if isinstance(d, dict) else {}
            if isinstance(werte, dict):
                kuerzel |= {str(k).split("|")[0].upper() for k in werte}
                for v in werte.values():
                    if isinstance(v, dict):
                        n = _kern(v.get("firma") or "")
                        if len(n) >= 5:
                            namen.add(n)
            elif isinstance(werte, list):
                kuerzel |= {str(x.get("ticker", x) if isinstance(x, dict) else x).split("|")[0].upper() for x in werte}
        except Exception:
            pass
    for pfad in (os.path.join(os.environ.get("DATEN_EINSTELLUNGEN", ".daten"), "blacklist", "blacklist.json"),
                 "blacklist.json"):
        try:
            with open(pfad, encoding="utf-8") as f:
                kuerzel |= {str(e.get("ticker", "")).split("|")[0].upper() for e in json.load(f).get("eintraege", [])}
        except Exception:
            pass
    kuerzel |= {t.strip().upper() for t in os.environ.get("VERITAS_MASKE_EXTRA", "").split(",")}
    return {t for t in kuerzel if re.fullmatch(r"[A-Z0-9.\-]{1,10}", t or "")}, namen


def _muster(woerter, grenze_vorn, grenze_hinten):
    if not woerter:
        return None
    return re.compile(grenze_vorn + "(?:" + "|".join(sorted((re.escape(w) for w in woerter), key=len, reverse=True))
                      + ")" + grenze_hinten)


class _Maske:
    def __init__(self, strom, ersetzen, zeilen_k, zeilen_n, ganze_zeilen):
        self._strom, self._ersetzen, self._zk, self._zn = strom, ersetzen, zeilen_k, zeilen_n
        self._ganze = ganze_zeilen
        self._rest = ""
        self._verwerfen = False
        self._sperre = threading.Lock()
        self.ausgeblendet = 0

    def _zeile(self, z):
        if self._ganze:
            if (self._zk is not None and self._zk.search(z)) or (self._zn is not None and self._zn.search(z)):
                self.ausgeblendet += 1
                return ""
            return z
        return self._ersetzen.sub("•••", z) if self._ersetzen is not None else z

    def _trifft(self, text):
        return (self._zk is not None and self._zk.search(text) is not None) or (
            self._zn is not None and self._zn.search(text) is not None)

    def write(self, text):
        try:
            if not isinstance(text, str):
                return self._strom.write(text)
            if not self._ganze:
                return self._strom.write(self._zeile(text))
            laenge = len(text)
            with self._sperre:
                if self._verwerfen:
                    i = text.find("\n")
                    if i < 0:
                        return laenge
                    text, self._verwerfen = text[i + 1:], False
                    if not text:
                        return laenge
                ganz = self._rest + text
                if self._trifft(ganz):
                    self.ausgeblendet += ganz.count("\n") + (0 if ganz.endswith("\n") else 1)
                    self._rest = ""
                    self._verwerfen = not text.endswith("\n")
                    return laenge
                self._rest += text
                if "\n" in self._rest:
                    teile = self._rest.split("\n")
                    self._rest = teile.pop()
                    self._strom.write("".join(z + "\n" for z in teile))
            return laenge
        except Exception:
            return len(text) if isinstance(text, str) else 0

    def schliessen(self):
        try:
            with self._sperre:
                rest, self._rest = self._rest, ""
            if rest:
                aus = self._zeile(rest)
                if aus:
                    self._strom.write(aus)
            self._strom.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._strom, name)


def _ohne_quelltext():
    import linecache
    wurzel = os.path.realpath(os.environ.get("GITHUB_WORKSPACE") or os.getcwd())
    alt_zeile, alt_zeilen, alt_neu = linecache.getline, linecache.getlines, linecache.updatecache

    def eigen(name):
        try:
            return os.path.realpath(str(name)).startswith(wurzel + os.sep)
        except Exception:
            return False

    def getline(name, lineno, module_globals=None):
        return "" if eigen(name) else alt_zeile(name, lineno, module_globals)

    def getlines(name, module_globals=None):
        return [] if eigen(name) else alt_zeilen(name, module_globals)

    def updatecache(name, module_globals=None):
        return [] if eigen(name) else alt_neu(name, module_globals)

    linecache.getline, linecache.getlines, linecache.updatecache = getline, getlines, updatecache


def _einschalten():
    if os.environ.get("VERITAS_MASKE") == "aus":
        return
    in_github = os.environ.get("GITHUB_ACTIONS") == "true"
    if in_github:
        _ohne_quelltext()
    kuerzel, namen = _laden()
    if not kuerzel and not namen:
        return
    ersetzen = _muster(kuerzel, r"(?<![A-Za-z0-9.\-])", r"(?![A-Za-z0-9\-]|\.[A-Za-z0-9])")
    zk = _muster({t for t in kuerzel if len(t) >= 2 and t not in _STOPP}, r"(?<![A-Za-z0-9.\-])",
                 r"(?![A-Za-z0-9\-]|\.[A-Za-z0-9])")
    zn = _muster(namen, r"(?<![\w])", r"(?![\w])")
    aus, fehler = sys.stdout, sys.stderr
    m_aus = _Maske(aus, ersetzen, zk, zn, in_github)
    m_fehler = _Maske(fehler, ersetzen, zk, zn, in_github)
    sys.stdout, sys.stderr = m_aus, m_fehler
    if in_github:
        import atexit

        def ende():
            m_aus.schliessen()
            m_fehler.schliessen()
            n = m_aus.ausgeblendet + m_fehler.ausgeblendet
            if n:
                try:
                    fehler.write(f"Maske: {n} Zeilen mit Listenbezug ausgeblendet.\n")
                    fehler.flush()
                except Exception:
                    pass

        atexit.register(ende)


try:
    _einschalten()
except Exception:
    pass
