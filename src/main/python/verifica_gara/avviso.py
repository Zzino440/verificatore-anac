"""Lettura dell'avviso ANAC: tipologia, lotti con CIG e link, valori dei campi da verificare
secondo campi.json."""
import json
import os
import re
import sys

with open(os.path.join(os.path.dirname(__file__), "campi.json"), encoding="utf-8") as _f:
    CONFIG = json.load(_f)


def pulisci_url(u):
    if not u:
        return None
    u = str(u).strip()
    m = re.search(r"\]\((https?://[^)\s]+)\)", u)  # [testo](url) da markdown/Notion
    if m:
        u = m.group(1)
    m = re.search(r"https?://[^\s<>\"'\]\)]+", u)
    return m.group(0) if m else None


def campi_della_tipologia(tipologia):
    """I campi attivi della tipologia, con livello 'lotto' (dentro items[?]) o 'avviso'."""
    if tipologia not in CONFIG:
        sys.exit(f"ERRORE: tipologia {tipologia!r} non prevista in campi.json. Tipologie note: "
                 + ", ".join(k for k in CONFIG if not k.startswith("_")))
    if not CONFIG[tipologia]["supportata"]:
        sys.exit(f"ERRORE: la tipologia {tipologia} non ha CIG e non è ancora gestita dalla verifica automatica.")
    campi = []
    for c in CONFIG[tipologia]["campi"]:
        if c["enable"]:
            lotto = "items[?]." in c["percorso"]
            rel = c["percorso"].split("items[?].", 1)[1] if lotto else c["percorso"]
            campi.append({**c, "livello": "lotto" if lotto else "avviso", "relativo": rel})
    return campi


def _vuoto(v):
    return v is None or (isinstance(v, str) and not v.strip())


def risolvi(nodo, percorso):
    """Valori non vuoti di un percorso come 'sections[A].fields.soggetti_sa[?].codice_fiscale'.
    sections[A] e' la sezione il cui nome inizia con 'SEZ. A'; [?], [!], [$] sono liste."""
    nodi = [nodo]
    for seg in percorso.split("."):
        m = re.fullmatch(r"(\w+)(?:\[(.)\])?", seg)
        chiave, sel = m.group(1), m.group(2)
        nuovi = []
        for n in nodi:
            v = n.get(chiave) if isinstance(n, dict) else None
            if sel is None:
                nuovi.append(v)
            elif isinstance(v, list):
                if sel.isalpha() and sel.isupper():
                    scelte = [s for s in v if isinstance(s, dict)
                              and re.match(r"SEZ\.?\s*%s\b" % sel, str(s.get("name", "")), re.I)]
                    i = ord(sel) - ord("A")
                    nuovi.extend(scelte or (v[i:i + 1]))
                else:
                    nuovi.extend(v)
        nodi = nuovi
    return [v for v in nodi if not _vuoto(v) and not isinstance(v, (dict, list))]


def leggi_avviso(path):
    """-> (idAvviso, tipologia, lotti). Ogni lotto: cig, url, valori {nome: [valori]},
    alternative dell'oggetto (metadata.descrizione e titolo)."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            avviso = json.load(f)
    except FileNotFoundError:
        sys.exit(f"ERRORE: file {path} non trovato nella cartella di lavoro {os.getcwd()}")
    except json.JSONDecodeError as e:
        sys.exit(f"ERRORE: {path} non e' un JSON valido ({e}).")
    tipologia = avviso.get("tipologia")
    campi = campi_della_tipologia(tipologia)
    tpl = avviso["templates"][0]["template"]
    meta = tpl.get("metadata") or {}
    alternative = [x for x in (meta.get("descrizione"), meta.get("titolo")) if not _vuoto(x)]
    link_gen, items = None, []
    for s in tpl.get("sections") or []:
        f = s.get("fields") or {}
        if f.get("documenti_di_gara_link"):
            link_gen = f["documenti_di_gara_link"]
        for it in s.get("items") or []:
            if it.get("tipo_oggetto", "lotto") == "lotto" or it.get("cig"):
                items.append(it)
    comuni = {c["nome"]: risolvi(tpl, c["percorso"]) for c in campi if c["livello"] == "avviso"}
    lotti = []
    for it in items:
        valori = {c["nome"]: (risolvi(it, c["relativo"]) if c["livello"] == "lotto" else comuni[c["nome"]])
                  for c in campi}
        lotti.append(_lotto(it.get("cig"), it.get("documenti_di_gara_link") or link_gen,
                            campi, valori, alternative))
    return avviso.get("idAvviso"), tipologia, lotti


def _lotto(cig, link, campi, valori, alternative):
    importi = [c for c in campi if c["livello"] == "lotto" and c["tipo"] == "importo"
               and "[" not in c["relativo"] and valori[c["nome"]]]
    return {
        "cig": str(cig or "").strip(),
        "url": pulisci_url(link),
        "campi": campi,
        "valori": valori,
        "alternative_oggetto": alternative,
        # l'importo principale del lotto: serve a dividere la pagina in blocchi e al caso "(diverso)"
        "campo_importo": importi[0]["nome"] if importi else None,
        "importo": valori[importi[0]["nome"]][0] if importi else None,
    }

