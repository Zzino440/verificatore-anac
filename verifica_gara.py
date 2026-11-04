"""Verifica che la pagina del link di gara riporti CIG, importo, scadenza e oggetto
di ogni lotto di un avviso ANAC. Solo libreria standard.

Si usa come modulo: controllo_link_gara (installato da installa.py, flusso skill)
oppure verifica_gara (copia nella cartella del progetto, flusso system prompt).
Uso dal tool python (nella cartella di lavoro), con <modulo> uno dei due:
  <modulo>.esegui("avviso.json", versione="N")
  <modulo>.esegui("avviso.json", versione="N", lotto=CIG, cig=.., importo=.., scadenza=.., oggetto=..)
  <modulo>.esegui("avviso.json", versione="N", nonraggiungibile=CIG)
Da riga di comando: python verifica.py avviso.json [--lotto CIG ...] [--nonraggiungibile CIG]
Ogni verifica va in esiti/AAAA-MM-GG/NNN_HH-MM-SS_<idAvviso>/ (avviso.json + esito.json),
con esiti/AAAA-MM-GG/riepilogo.md che elenca le verifiche del giorno.
"""
import argparse
import glob
import json
import os
import re
import shutil
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from html.parser import HTMLParser

sys.stdout.reconfigure(encoding="utf-8")

VERSIONE = "6"  # deve coincidere con quella scritta nelle istruzioni (SKILL.md e prompt-di-sistema.md)
CARTELLA_ESITI = "esiti"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
ORDINE = {"verificato": 0, "dubbio": 1, "non_verificabile": 2}
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


# ---------- avviso ----------

def pulisci_url(u):
    if not u:
        return None
    u = str(u).strip()
    m = re.search(r"\]\((https?://[^)\s]+)\)", u)  # [testo](url) da markdown/Notion
    if m:
        u = m.group(1)
    m = re.search(r"https?://[^\s<>\"'\]\)]+", u)
    return m.group(0) if m else None


def leggi_avviso(path):
    try:
        with open(path, "rb") as f:
            raw = f.read()
        try:
            testo = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            testo = raw.decode("cp850")  # file scritto con echo dal prompt di Windows
        avviso = json.loads(testo)
    except FileNotFoundError:
        sys.exit(f"ERRORE: file {path} non trovato nella cartella di lavoro {os.getcwd()}")
    except json.JSONDecodeError as e:
        id_avviso, lotti = leggi_per_campi(testo)
        if not lotti:
            sys.exit(f"ERRORE: {path} non e' un JSON valido ({e}) e non contiene nessun cig. "
                     "Riscrivi il file copiando esattamente il testo incollato dall'utente.")
        print("NOTA: JSON con parentesi sbagliate, valori letti campo per campo.")
        return id_avviso, lotti
    tpl = avviso["templates"][0]["template"]
    meta_desc = (tpl.get("metadata") or {}).get("descrizione") or ""
    link_gen, items = None, []
    for s in tpl.get("sections") or []:
        f = s.get("fields") or {}
        if f.get("documenti_di_gara_link"):
            link_gen = f["documenti_di_gara_link"]
        for it in s.get("items") or []:
            if it.get("tipo_oggetto", "lotto") == "lotto":
                items.append(it)
    lotti = []
    for it in items:
        lotti.append({
            "cig": (it.get("cig") or "").strip(),
            "descrizione": it.get("descrizione") or "",
            "meta_desc": meta_desc,
            "importo": it.get("valore_complessivo_stimato"),
            "scadenza": it.get("termine_ricezione"),
            "url": pulisci_url(it.get("documenti_di_gara_link")) or pulisci_url(link_gen),
        })
    return avviso.get("idAvviso"), lotti


def _stringa(chiave, testo):
    m = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % chiave, testo)
    return json.loads('"' + m.group(1) + '"') if m else None


def leggi_per_campi(testo):
    """Ripiego se il JSON e' rotto (es. una parentesi persa ricopiandolo):
    ogni "cig" apre un lotto, i suoi campi sono quelli che seguono fino al cig successivo."""
    m = re.search(r'"metadata"\s*:\s*\{[^{}]*', testo)
    meta_desc = (_stringa("descrizione", m.group(0)) if m else None) or ""
    link_gen = _stringa("documenti_di_gara_link", testo)
    inizi = [m.start() for m in re.finditer(r'"cig"\s*:', testo)]
    lotti = []
    for i, start in enumerate(inizi):
        pezzo = testo[start:inizi[i + 1] if i + 1 < len(inizi) else len(testo)]
        imp = re.search(r'"valore_complessivo_stimato"\s*:\s*"?([\d.]+)', pezzo)
        lotti.append({
            "cig": (_stringa("cig", pezzo) or "").strip(),
            "descrizione": _stringa("descrizione", pezzo) or "",
            "meta_desc": meta_desc,
            "importo": float(imp.group(1)) if imp else None,
            "scadenza": _stringa("termine_ricezione", pezzo),
            "url": pulisci_url(_stringa("documenti_di_gara_link", pezzo)) or pulisci_url(link_gen),
        })
    return _stringa("idAvviso", testo), lotti


# ---------- pagina ----------

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
        return {"problema": f"errore HTTP {e.code}"}
    except Exception as e:  # rete, SSL, timeout
        return {"problema": f"errore di rete: {str(e)[:100]}"}
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
    if not stesso:
        out["problema"] = (f"redirect a {finale}; se anche il tool web arriva a una pagina senza il CIG, "
                           "usa nonraggiungibile")
    elif len(testo) < 500:
        out["problema"] = "pagina quasi vuota (forse caricata via JavaScript)"
    return out


# ---------- confronti ----------

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
        esito, motivo = "non_verificabile", "CIG non presente nella pagina"
    elif mancano:
        esito = "dubbio"
        motivo = "non coincide o manca: " + ", ".join(mancano)
        if stato == "orario_diverso":
            motivo += " (data giusta, orario diverso)"
        if diverso:
            motivo += f" (importo nella pagina {diverso}, nell'avviso {lotto['importo']})"
    else:
        esito, motivo = "verificato", "CIG, importo, scadenza e oggetto trovati"
    return {"cig": lotto["cig"], "url": lotto["url"], "url_finale": url_finale or lotto["url"],
            "fonte": fonte, "campi": campi, "esito": esito, "motivo": motivo}


# ---------- output ----------

def corto(v, n=55):
    s = "-" if v is None else str(v)
    return s if len(s) <= n else s[:n] + "..."


def stampa(id_avviso, risultati):
    print(f"Avviso {id_avviso}")
    for r in risultati:
        print(f"\nLotto {r['cig']} | fonte: {r.get('fonte', '-')} | URL: {r['url']}")
        if r["esito"] == "da_completare":
            print(f"Pagina non utilizzabile dallo script: {r['motivo']}")
            continue
        print("| campo | atteso | trovato | ok |\n|---|---|---|---|")
        for k, v in r["campi"].items():
            print(f"| {k} | {corto(v['atteso'])} | {corto(v['trovato'])} | {'si' if v['ok'] else 'NO'} |")
        estratti = [(k, v["estratto"]) for k, v in r["campi"].items() if v.get("estratto")]
        if estratti:
            print("Dove compaiono nella pagina scaricata:")
            for k, e in estratti:
                print(f"- {k}: \"{e}\"")
        print(f"Esito lotto: {r['esito']} - {r['motivo']}")
    aperti = [r for r in risultati if r["esito"] == "da_completare"]
    if aperti:
        print("\nAZIONE RICHIESTA: usa il tool web come indicato al passo 2 delle istruzioni per questi lotti:")
        for r in aperti:
            print(f"FALLBACK_WEB {r['url']} lotto {r['cig']} ({r['motivo']})")
        return None
    finale = max((r["esito"] for r in risultati), key=ORDINE.get)
    print(f"\nESITO FINALE: {finale}")
    return finale


def esegui(avviso="avviso.json", versione=None, lotto=None, cig="", importo="", scadenza="",
           oggetto="", nonraggiungibile=None):
    """Punto di ingresso per il tool python:
    import <modulo>; <modulo>.esegui("avviso.json", versione="...")"""
    if versione is not None and str(versione) != VERSIONE:
        skill = __name__ != "verifica_gara"
        if str(versione).isdigit() and int(versione) < int(VERSIONE):
            vecchio = "le istruzioni sono vecchie"
            rimedio = ("aggiornare SKILL.md" if skill else
                       "reincollare prompt-di-sistema.md nel System prompt e aprire una nuova chat nel progetto")
        else:
            vecchio = f"il modulo {__name__} e' vecchio"
            rimedio = ("rilanciare installa.py della skill" if skill else
                       "ricopiare verifica_gara.py nella cartella del progetto")
        print(f"ERRORE di versione: le istruzioni chiedono la versione {versione}, il modulo {__name__} "
              f"e' la {VERSIONE}, quindi {vecchio}. Di' all'utente di {rimedio}.")
        return
    try:
        _esegui(avviso, lotto, cig, importo, scadenza, oggetto, nonraggiungibile)
    except SystemExit as e:  # gli errori previsti escono con un messaggio, non con un traceback
        print(e)


def _esegui(avviso, lotto, cig, importo, scadenza, oggetto, nonraggiungibile):
    id_avviso, lotti = leggi_avviso(avviso)
    if not lotti:
        sys.exit("ERRORE: nessun lotto trovato nell'avviso (sections -> items con tipo_oggetto 'lotto').")

    bersaglio = lotto or nonraggiungibile
    if bersaglio and bersaglio not in {l["cig"] for l in lotti}:
        sys.exit(f"ERRORE: CIG {bersaglio} non presente nell'avviso. CIG validi: "
                 + ", ".join(l["cig"] for l in lotti))

    run = cartella_run(id_avviso, nuova=not bersaglio)
    if not bersaglio:
        shutil.copyfile(avviso, os.path.join(run, "avviso.json"))
    print(f"Cartella di questa verifica: {run.replace(os.sep, '/')}")
    file_esito = os.path.join(run, "esito.json")

    precedenti = {}
    if os.path.exists(file_esito):
        try:
            with open(file_esito, encoding="utf-8") as f:
                old = json.load(f)
            if old.get("idAvviso") == id_avviso:
                precedenti = {r["cig"]: r for r in old.get("lotti", [])}
        except (json.JSONDecodeError, KeyError):
            pass

    cache, risultati = {}, []
    for l in lotti:
        if bersaglio and l["cig"] != bersaglio and l["cig"] in precedenti:
            risultati.append(precedenti[l["cig"]])
            continue
        if nonraggiungibile == l["cig"]:
            risultati.append({"cig": l["cig"], "url": l["url"], "fonte": "web", "campi": {},
                              "esito": "non_verificabile",
                              "motivo": "pagina non raggiungibile neanche con il tool web"})
            continue
        if lotto == l["cig"]:
            testi = {"cig": cig, "importo": importo, "scadenza": scadenza, "oggetto": oggetto}
            risultati.append(valuta(l, testi, "web"))
            continue
        if not l["url"]:
            risultati.append({"cig": l["cig"], "url": None, "fonte": "script", "campi": {},
                              "esito": "non_verificabile", "motivo": "link di gara assente nell'avviso"})
            continue
        if l["url"] not in cache:
            print(f"Scarico la pagina {l['url']} ...")
            cache[l["url"]] = scarica(l["url"])
            info = cache[l["url"]].get("pagina")
            if info:
                print(f"  risposta HTTP {info['http']}, {info['caratteri']} caratteri di testo, "
                      f"titolo della pagina: \"{info['titolo']}\"")
            if cache[l["url"]].get("problema"):
                print(f"  problema: {cache[l['url']]['problema']}")
        pag = cache[l["url"]]
        if pag.get("problema"):
            risultati.append({"cig": l["cig"], "url": l["url"], "url_finale": pag.get("url_finale"),
                              "fonte": "script", "campi": {}, "esito": "da_completare",
                              "motivo": pag["problema"]})
            continue
        t = pag["testo"]
        if "blocchi" not in pag:
            pag["blocchi"] = blocchi_lotti(t, [x for x in lotti if x["url"] == l["url"]])
        bl = pag["blocchi"].get(l["cig"])
        # importo e oggetto nel pezzo di pagina del lotto; se il blocco non ha importi
        # (es. importi in una tabella separata) l'importo si cerca in tutta la pagina
        t_imp = bl if bl and re.search(IMPORTO_RX, bl, re.I) else t
        r = valuta(l, {"cig": t, "importo": t_imp, "scadenza": t, "oggetto": bl or t}, "script",
                   pag["url_finale"], importo_della_pagina(t_imp, blocco=t_imp is bl))
        r["pagina"] = pag["pagina"]
        if not r["campi"]["cig"]["ok"]:
            r["esito"], r["motivo"] = "da_completare", "CIG non trovato nella pagina scaricata"
        risultati.append(r)

    finale = stampa(id_avviso, risultati)
    with open(file_esito, "w", encoding="utf-8") as f:
        json.dump({"idAvviso": id_avviso, "esito": finale or "da_completare", "lotti": risultati},
                  f, ensure_ascii=False, indent=2)
    aggiorna_riepilogo(os.path.dirname(run))
    print(f"Risultato salvato in {file_esito.replace(os.sep, '/')}")


def cartella_run(id_avviso, nuova):
    """Nuova verifica: esiti/AAAA-MM-GG/NNN_HH-MM-SS_<idAvviso>, con NNN progressivo del giorno.
    Ripiego web (nuova=False): l'ultima cartella dello stesso avviso, che va completata."""
    nome = re.sub(r"[^\w.-]", "_", str(id_avviso or "avviso"))
    if not nuova:
        esistenti = sorted(glob.glob(os.path.join(CARTELLA_ESITI, "*", f"[0-9][0-9][0-9]_*_{nome}")))
        if esistenti:
            return esistenti[-1]
    ora = datetime.now()
    giorno = os.path.join(CARTELLA_ESITI, ora.strftime("%Y-%m-%d"))
    os.makedirs(giorno, exist_ok=True)
    num = 1 + max((int(n[:3]) for n in os.listdir(giorno) if n[:3].isdigit()), default=0)
    run = os.path.join(giorno, f"{num:03d}_{ora:%H-%M-%S}_{nome}")
    os.makedirs(run)
    return run


def aggiorna_riepilogo(giorno):
    """Riscrive riepilogo.md del giorno: una riga per verifica, con esito e cartella."""
    righe = [f"# Verifiche del {os.path.basename(giorno)}", "",
             "| n. | ora | avviso | esito | cartella |", "|---|---|---|---|---|"]
    for nome in sorted(os.listdir(giorno)):
        p = os.path.join(giorno, nome, "esito.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                e = json.load(f)
            righe.append(f"| {nome[:3]} | {nome[4:12].replace('-', ':')} | {e.get('idAvviso')} | "
                         f"{e.get('esito')} | {nome} |")
    with open(os.path.join(giorno, "riepilogo.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(righe) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("avviso")
    ap.add_argument("--lotto", help="CIG del lotto verificato col tool web")
    ap.add_argument("--cig", default="")
    ap.add_argument("--importo", default="")
    ap.add_argument("--scadenza", default="")
    ap.add_argument("--oggetto", default="")
    ap.add_argument("--nonraggiungibile", metavar="CIG")
    a = ap.parse_args()
    esegui(a.avviso, None, a.lotto, a.cig, a.importo, a.scadenza, a.oggetto, a.nonraggiungibile)


if __name__ == "__main__":
    main()
