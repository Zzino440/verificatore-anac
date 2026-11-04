"""Lettura dell'avviso ANAC: lotti con CIG, importo, scadenza, oggetto e link."""
import json
import os
import re
import sys


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
