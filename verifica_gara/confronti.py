"""Confronto dei campi del lotto (CIG, importo, scadenza, oggetto) con il testo della pagina."""
import re
import unicodedata
from datetime import datetime, timedelta

MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "enero": 1, "febrero": 2, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
     "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
STOPWORD = set("""della delle dello degli dell nella nelle nello negli alla alle allo agli
dalla dalle dallo dagli sulla sulle sullo sugli come anche sono questo questa quello quella
per con tra fra dei del les des para como este esta estos estas entre sobre with from that
this their which into the and los las del que una uno""".split())


def num_candidati(tok):
    tok = tok.replace("'", "")
    if "." in tok and "," in tok:
        if tok.rfind(",") > tok.rfind("."):
            tok = tok.replace(".", "").replace(",", ".")
        else:
            tok = tok.replace(",", "")
        return [tok]
    for sep, dec in ((",", "."), (".", ",")):
        if sep in tok:
            if re.fullmatch(r"\d{1,3}(\%s\d{3})+" % sep, tok):
                c = [tok.replace(sep, "")]
                if tok.count(sep) == 1:
                    c.append(tok.replace(sep, "."))
                return c
            if tok.count(sep) == 1:
                return [tok.replace(sep, ".")]
            return []
    return [tok]


def cerca_importo(atteso, testo):
    if atteso is None:
        return None
    for m in re.finditer(r"\d[\d.,']*\d|\d", testo):
        for c in num_candidati(m.group()):
            try:
                if abs(float(c) - float(atteso)) < 0.01:
                    return m.group()
            except ValueError:
                pass
    return None


IMPORTO_RX = r"€\s*\d[\d.,']*\d|\d[\d.,']*\d\s*(?:€|euro\b|eur\b)"


def importo_della_pagina(testo, blocco):
    """L'importo che la pagina indica per il lotto: il primo importo del suo blocco,
    oppure, senza blocco, il primo importo scritto subito dopo la parola 'importo'."""
    if blocco:
        m = re.search(IMPORTO_RX, testo, re.I)
        return m.group() if m else None
    m = re.search(r"importo[^€\d]{0,60}(" + IMPORTO_RX + ")", testo, re.I)
    return m.group(1) if m else None


def blocchi_lotti(testo, lotti):
    """CIG -> pezzo di pagina che riguarda quel lotto, se la pagina elenca piu' lotti.
    Prova i due ordini possibili (dati dopo il proprio CIG o prima) e tiene quello
    in cui ritrova piu' importi attesi; a parita', dati dopo il CIG."""
    low = testo.lower()
    pos = sorted((low.find(l["cig"].lower()), l["cig"]) for l in lotti
                 if l["cig"] and l["cig"].lower() in low)
    if len(pos) < 2:
        return {}
    inizi = [p for p, _ in pos]
    lung = max(b - a for a, b in zip(inizi, inizi[1:]))
    dopo = {c: testo[p:inizi[i + 1] if i + 1 < len(inizi) else p + lung]
            for i, (p, c) in enumerate(pos)}
    prima = {c: testo[inizi[i - 1] + len(pos[i - 1][1]) if i else max(0, p - lung):p + len(c)]
             for i, (p, c) in enumerate(pos)}
    importi = {l["cig"]: l["importo"] for l in lotti}
    presi = lambda bl: sum(cerca_importo(importi[c], t) is not None for c, t in bl.items())
    return prima if presi(prima) > presi(dopo) else dopo


def date_nel_testo(testo):
    """Restituisce (data, orario o None, testo trovato)."""
    t = testo.lower()
    trovate = []
    regole = [
        (r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b", lambda g: (int(g[2]), int(g[1]), int(g[0]))),
        (r"\b(\d{4})-(\d{2})-(\d{2})", lambda g: (int(g[0]), int(g[1]), int(g[2]))),
        (r"\b(\d{1,2})\s+(?:de\s+)?([a-zà-ú]+)\s+(?:de\s+|del\s+)?(\d{4})\b",
         lambda g: (int(g[2]), MESI.get(g[1]), int(g[0]))),
    ]
    for rx, conv in regole:
        for m in re.finditer(rx, t):
            try:
                y, mo, d = conv(m.groups())
                data = datetime(y, mo, d).date()
            except (TypeError, ValueError):
                continue
            dopo = t[m.end():m.end() + 25]
            h = re.search(r"(\d{1,2})[:.](\d{2})", dopo)
            orario = (int(h.group(1)), int(h.group(2))) if h else None
            trovate.append((data, orario, testo[m.start():m.end() + (h.end() if h else 0)].strip()))
    return trovate


def accettati(iso):
    """Coppie (data, orario) ammesse: come scritto e convertito in ora italiana (+1/+2 da UTC)."""
    dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    ok = {(dt.date(), (dt.hour, dt.minute))}
    if dt.utcoffset() is not None:
        utc = dt.replace(tzinfo=None) - dt.utcoffset()
        for ore in (1, 2):
            x = utc + timedelta(hours=ore)
            ok.add((x.date(), (x.hour, x.minute)))
    return ok


def cerca_scadenza(atteso, testo):
    """-> (stato, trovato) con stato in ok / orario_diverso / no."""
    if not atteso:
        return "no", None
    ok = accettati(atteso)
    date_ok = {d for d, _ in ok}
    diverso = None
    senza_ora = None
    for data, orario, s in date_nel_testo(testo):
        if data not in date_ok:
            continue
        if orario is None:
            senza_ora = senza_ora or s
        elif (data, orario) in ok:
            return "ok", s
        else:
            diverso = diverso or s
    if diverso:
        return "orario_diverso", diverso
    if senza_ora:
        return "ok", senza_ora + " (ora non indicata)"
    return "no", None


def parole(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return [w for w in re.findall(r"[a-z0-9]+", s) if len(w) > 3 and w not in STOPWORD]


def copertura_oggetto(lotto, testo, fonte):
    """Pagina intera: quota di parole dell'oggetto presenti nella pagina.
    Tool web: il modello copia solo un pezzo del titolo, quindi conta la quota
    delle parole copiate (almeno 3) che compaiono nell'oggetto atteso."""
    pagina = set(parole(testo))
    migliore = 0.0
    for desc in (lotto["descrizione"], lotto["meta_desc"]):
        w = set(parole(desc))
        if fonte == "web":
            if len(pagina) >= 3:
                migliore = max(migliore, len(w & pagina) / len(pagina))
        elif w:
            migliore = max(migliore, len(w & pagina) / len(w))
    return migliore


def estratto(testo, frammento, margine=60):
    """Il pezzo di pagina attorno a frammento, come prova di dove e' stato trovato."""
    if not frammento:
        return None
    i = testo.lower().find(frammento.lower())
    if i < 0:
        return None
    a, b = max(0, i - margine), min(len(testo), i + len(frammento) + margine)
    return ("..." if a else "") + testo[a:b] + ("..." if b < len(testo) else "")


def estratto_oggetto(lotto, testo):
    """Il tratto piu' lungo dell'oggetto (almeno 3 parole, dall'inizio) che compare nella pagina."""
    for desc in (lotto["descrizione"], lotto["meta_desc"]):
        w = desc.split()
        for n in range(len(w), 2, -1):
            e = estratto(testo, " ".join(w[:n]))
            if e:
                return e
    return None


def valuta(lotto, testi, fonte, url_finale=None, importo_pagina=None):
    """testi: dict campo -> testo in cui cercare (pagina intera, blocco del lotto o stringa
    copiata dal modello). importo_pagina: l'importo che la pagina indica per il lotto."""
    campi = {}
    cig_ok = bool(lotto["cig"]) and lotto["cig"].lower() in testi["cig"].lower()
    campi["cig"] = {"atteso": lotto["cig"], "trovato": lotto["cig"] if cig_ok else None, "ok": cig_ok}
    imp = cerca_importo(lotto["importo"], testi["importo"])
    campi["importo"] = {"atteso": lotto["importo"], "trovato": imp, "ok": imp is not None}
    diverso = None if imp else importo_pagina
    if diverso:
        campi["importo"]["trovato"] = f"{diverso} (diverso)"
    stato, s = cerca_scadenza(lotto["scadenza"], testi["scadenza"])
    campi["scadenza"] = {"atteso": lotto["scadenza"], "trovato": s, "ok": stato == "ok"}
    cop = copertura_oggetto(lotto, testi["oggetto"], fonte)
    campi["oggetto"] = {"atteso": lotto["descrizione"] or lotto["meta_desc"],
                        "trovato": f"copertura parole {cop:.0%}", "ok": cop >= 0.5}
    if fonte == "script":
        campi["cig"]["estratto"] = estratto(testi["cig"], campi["cig"]["trovato"])
        campi["importo"]["estratto"] = estratto(testi["importo"], imp or diverso)
        campi["scadenza"]["estratto"] = estratto(testi["scadenza"], (s or "").replace(" (ora non indicata)", ""))
        campi["oggetto"]["estratto"] = estratto_oggetto(lotto, testi["oggetto"])
    mancano = [k for k, v in campi.items() if not v["ok"]]
    if not cig_ok:
        esito, causa, motivo = "non_verificabile", "cig_assente", f"la pagina non riporta il CIG {lotto['cig']}"
    elif mancano:
        esito, causa = "dubbio", "campi_diversi"
        motivo = "la pagina riporta il CIG, ma non coincide o manca: " + ", ".join(mancano)
        if stato == "orario_diverso":
            motivo += " (data giusta, orario diverso)"
        if diverso:
            motivo += f" (importo nella pagina {diverso}, nell'avviso {euro(lotto['importo'])})"
    else:
        esito, causa, motivo = "verificato", "tutto_trovato", "la pagina riporta CIG, importo, scadenza e oggetto"
    return {"cig": lotto["cig"], "url": lotto["url"], "url_finale": url_finale or lotto["url"],
            "fonte": fonte, "campi": campi, "esito": esito, "causa": causa, "motivo": motivo}


def euro(v):
    """5227740.17 -> € 5.227.740,17"""
    try:
        return "€ " + f"{float(v):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    except (TypeError, ValueError):
        return str(v)
