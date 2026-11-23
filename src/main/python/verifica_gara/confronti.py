"""Confronto dei campi del lotto (quelli attivi in campi.json) con il testo della pagina."""
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
    """-> (stato, trovato) con stato in ok / orario_diverso / no.
    Se l'avviso riporta solo la data (es. data_stipula_contratto), l'orario non conta."""
    if not atteso:
        return "no", None
    if "T" not in str(atteso):
        giorno = datetime.fromisoformat(str(atteso)[:10]).date()
        for data, _, s in date_nel_testo(testo):
            if data == giorno:
                return "ok", s
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


def copertura_testo(attesi, testo):
    """Quota di parole del testo atteso presenti nella pagina (il migliore tra gli attesi)."""
    pagina = set(parole(testo))
    migliore = 0.0
    for desc in attesi:
        w = set(parole(str(desc)))
        if w:
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


def estratto_testo(attesi, testo):
    """Il tratto piu' lungo del testo atteso (almeno 3 parole, dall'inizio) che compare nella pagina."""
    for desc in attesi:
        w = str(desc).split()
        for n in range(len(w), 2, -1):
            e = estratto(testo, " ".join(w[:n]))
            if e:
                return e
    return None


def _codice(s):
    return re.sub(r"\s", "", str(s)).lower()


def confronta(campo, valore, testo, alternative=()):
    """Un valore di un campo contro un testo. -> (ok, trovato, frammento per l'estratto, stato data)."""
    tipo = campo["tipo"]
    if tipo == "codice":
        ok = _codice(valore) in _codice(testo)
        return ok, str(valore) if ok else None, str(valore), None
    if tipo == "importo":
        try:
            imp = cerca_importo(float(valore), testo)
        except (TypeError, ValueError):
            imp = None
        return imp is not None, imp, imp, None
    if tipo == "data":
        stato, s = cerca_scadenza(valore, testo)
        return stato == "ok", s, (s or "").replace(" (ora non indicata)", ""), stato
    if tipo == "testo":
        attesi = [valore, *alternative]
        cop = copertura_testo(attesi, testo)
        return cop >= 0.5, f"copertura parole {cop:.0%}", attesi, None
    return None, "confronto non disponibile", None, None  # sino, link


def valuta(lotto, pagina, blocco, url_finale, importo_pagina=None):
    """Confronta i campi attivi del lotto con la pagina (testo intero) e con il blocco del lotto
    (pezzo di pagina che lo riguarda, o None).
    importo_pagina: l'importo che la pagina indica per il lotto (caso "(diverso)")."""
    campi, stati_data, diverso = {}, [], None
    for c in lotto["campi"]:
        valori = lotto["valori"][c["nome"]]
        voce = {"atteso": valori[0] if len(valori) == 1 else (valori or None)}
        if not valori:
            voce.update(trovato="non previsto", ok=None)
            campi[c["nome"]] = voce
            continue
        if (c["livello"] == "lotto" and c["tipo"] in ("importo", "testo") and blocco
                and (c["tipo"] == "testo" or re.search(IMPORTO_RX, blocco, re.I))):
            # importi e testi del lotto nel suo pezzo di pagina; senza importi nel blocco
            # (es. importi in una tabella separata) l'importo si cerca in tutta la pagina
            t = blocco
        else:
            t = pagina
        alt = lotto["alternative_oggetto"] if c["nome"] == "descrizione" else ()
        esiti = [confronta(c, v, t, alt) for v in valori]
        ok = None if any(e[0] is None for e in esiti) else all(e[0] for e in esiti)
        trovati = [e[1] for e in esiti if e[1]]
        voce.update(trovato="; ".join(trovati) if trovati else None, ok=ok)
        stati_data += [e[3] for e in esiti if e[3]]
        fr = next((e[2] for e in esiti if e[0]), None)  # cosa mostrare come estratto
        if ok is False and c["nome"] == lotto["campo_importo"] and importo_pagina:
            diverso = fr = importo_pagina
            voce["trovato"] = f"{diverso} (diverso)"
        voce["estratto"] = estratto_testo(fr, t) if isinstance(fr, list) else estratto(t, fr)
        campi[c["nome"]] = voce
    cig_ok = bool(campi.get("cig", {}).get("ok"))
    mancano = [k for k, v in campi.items() if v["ok"] is False]
    if not cig_ok:
        esito, causa, motivo = "non_verificabile", "cig_assente", f"la pagina non riporta il CIG {lotto['cig']}"
    elif mancano:
        esito, causa = "dubbio", "campi_diversi"
        motivo = "la pagina riporta il CIG, ma non coincide o manca: " + ", ".join(mancano)
        if "orario_diverso" in stati_data:
            motivo += " (data giusta, orario diverso)"
        if diverso:
            motivo += f" (importo nella pagina {diverso}, nell'avviso {euro(lotto['importo'])})"
    else:
        controllati = [k for k, v in campi.items() if v["ok"]]
        esito, causa = "verificato", "tutto_trovato"
        motivo = "la pagina riporta tutti i campi controllati: " + ", ".join(controllati)
    return {"cig": lotto["cig"], "url": lotto["url"], "url_finale": url_finale, "campi": campi, "esito": esito, "causa": causa, "motivo": motivo}


def euro(v):
    """5227740.17 -> € 5.227.740,17"""
    try:
        return "€ " + f"{float(v):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    except (TypeError, ValueError):
        return str(v)
