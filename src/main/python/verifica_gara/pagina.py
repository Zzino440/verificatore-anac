"""Scaricamento della pagina del link di gara e ricerca dei CIG che riporta."""
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class Testo(HTMLParser):
    SALTA = {"script", "style", "noscript", "template", "svg"}

    def __init__(self):
        super().__init__()
        self.parti, self.salta = [], 0
        self.titolo, self.in_titolo = "", False

    def handle_starttag(self, tag, attrs):
        if tag in self.SALTA:
            self.salta += 1
        if tag == "title":
            self.in_titolo = True

    def handle_endtag(self, tag):
        if tag in self.SALTA and self.salta:
            self.salta -= 1
        if tag == "title":
            self.in_titolo = False

    def handle_data(self, data):
        if self.in_titolo:
            self.titolo += data
        if not self.salta:
            self.parti.append(data)


def scarica(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "it,en;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            stato_http = r.status
            finale = r.geturl()
            raw = r.read()
            charset = r.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as e:
        return {"problema": f"lo script non riesce ad aprire la pagina (errore HTTP {e.code})"}
    except Exception as e:  # rete, SSL, timeout
        return {"problema": f"lo script non riesce ad aprire la pagina (errore di rete: {str(e)[:100]})"}
    p = Testo()
    p.feed(raw.decode(charset, "replace"))
    testo = re.sub(r"\s+", " ", " ".join(p.parti).replace("\xa0", " ")).strip()
    a, b = urllib.parse.urlparse(url), urllib.parse.urlparse(finale)
    stesso = (a.netloc.lower().removeprefix("www.") == b.netloc.lower().removeprefix("www.")
              and a.path.rstrip("/") == b.path.rstrip("/"))
    out = {"url_finale": finale, "testo": testo,
           "pagina": {"http": stato_http, "caratteri": len(testo),
                      "titolo": re.sub(r"\s+", " ", p.titolo).strip(),
                      "scaricata_il": datetime.now().isoformat(timespec="seconds")}}
    # non bloccano l'analisi: spiegano il motivo se il CIG manca
    if not stesso:
        out["nota"] = f"il link reindirizza a un'altra pagina ({finale})"
    elif len(testo) < 500:
        out["nota"] = "la pagina è quasi vuota (forse caricata via JavaScript)"
    return out


def cig_nella_pagina(testo):
    """I codici scritti dopo la parola CIG (10 caratteri, maiuscole e cifre), senza ripetizioni."""
    trovati = []
    for m in re.finditer(r"\bCIG\b\W{0,10}([A-Za-z0-9]{10})\b", testo, re.I):
        c = m.group(1)
        if c.isupper() and re.search(r"\d", c) and c not in trovati:
            trovati.append(c)
    return trovati
