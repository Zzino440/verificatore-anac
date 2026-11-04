"""Verifica che la pagina del link di gara riporti CIG, importo, scadenza e oggetto
di ogni lotto di un avviso ANAC. Solo libreria standard.

Uso dal tool python (nella cartella di lavoro), come da prompt-di-sistema.md:
  verifica_gara.esegui("avviso.json", versione="N")
  verifica_gara.esegui("avviso.json", versione="N", lotto=CIG, cig=.., importo=.., scadenza=.., oggetto=..)
  verifica_gara.esegui("avviso.json", versione="N", cigassente=CIG)
  verifica_gara.esegui("avviso.json", versione="N", nonraggiungibile=CIG)
Da riga di comando: python -m verifica_gara avviso.json [--lotto CIG ...] [--cigassente CIG] [--nonraggiungibile CIG]
Ogni verifica va in esiti/AAAA-MM-GG/NNN_HH-MM-SS_<idAvviso>/ (avviso.json + esito.json),
con esiti/AAAA-MM-GG/riepilogo.md che elenca le verifiche del giorno.
"""
import argparse
import json
import os
import re
import shutil
import sys

from .avviso import leggi_avviso
from .confronti import IMPORTO_RX, blocchi_lotti, estratto, importo_della_pagina, valuta
from .pagina import cig_nella_pagina, scarica
from .risposta import aggiorna_riepilogo, cartella_run, stampa

sys.stdout.reconfigure(encoding="utf-8")

VERSIONE = "0.0.1"  # semver, uguale a versione="..." in prompt-di-sistema.md


def _semver(v):
    """'0.1.2' -> (0, 1, 2); None se non e' una versione semver."""
    parti = str(v).split(".")
    return tuple(int(p) for p in parti) if len(parti) == 3 and all(p.isdigit() for p in parti) else None


def esegui(avviso="avviso.json", versione=None, lotto=None, cig="", importo="", scadenza="",
           oggetto="", nonraggiungibile=None, cigassente=None):
    """Punto di ingresso per il tool python:
    import <modulo>; <modulo>.esegui("avviso.json", versione="...")
    Prompt e modulo sono compatibili se coincidono major e minor: una patch non obbliga a
    reincollare il prompt."""
    chiesta, mia = _semver(versione), _semver(VERSIONE)
    if versione is not None and (chiesta is None or chiesta[:2] != mia[:2]):
        if chiesta is None or chiesta[:2] < mia[:2]:
            vecchio = "le istruzioni sono vecchie"
            rimedio = "reincollare prompt-di-sistema.md nel System prompt e aprire una nuova chat nel progetto"
        else:
            vecchio = f"il modulo {__name__} e' vecchio"
            rimedio = "ricopiare la cartella verifica_gara nella cartella del progetto"
        print(f"ERRORE di versione: le istruzioni chiedono la versione {versione}, il modulo {__name__} "
              f"e' la {VERSIONE}, quindi {vecchio}. Di' all'utente di {rimedio}.")
        return
    try:
        _esegui(avviso, lotto, cig, importo, scadenza, oggetto, nonraggiungibile, cigassente)
    except SystemExit as e:  # gli errori previsti escono con un messaggio, non con un traceback
        print(e)


def _esegui(avviso, lotto, cig, importo, scadenza, oggetto, nonraggiungibile, cigassente):
    id_avviso, lotti = leggi_avviso(avviso)
    if not lotti:
        sys.exit("ERRORE: nessun lotto trovato nell'avviso (sections -> items con tipo_oggetto 'lotto').")

    bersaglio = lotto or nonraggiungibile or cigassente
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
        # ripiego web: si tengono le prove della prima chiamata (risposta HTTP, motivo dello script)
        prima = precedenti.get(l["cig"], {})
        motivo_script = prima.get("motivo_script") or (prima.get("motivo") if prima.get("fonte") == "script" else None)
        if l["cig"] in (nonraggiungibile, cigassente):
            if nonraggiungibile == l["cig"]:
                causa, motivo = "pagina_non_raggiungibile", "la pagina non si apre né con lo script né con il tool web"
            else:
                causa, motivo = "cig_assente", f"anche con il tool web la pagina non riporta il CIG {l['cig']}"
            risultati.append({"cig": l["cig"], "url": l["url"], "fonte": "web", "campi": {},
                              "pagina": prima.get("pagina"), "motivo_script": motivo_script,
                              "esito": "non_verificabile", "causa": causa, "motivo": motivo})
            continue
        if lotto == l["cig"]:
            testi = {"cig": cig, "importo": importo, "scadenza": scadenza, "oggetto": oggetto}
            r = valuta(l, testi, "web")
            r["pagina"], r["motivo_script"] = prima.get("pagina"), motivo_script
            risultati.append(r)
            continue
        if not l["url"]:
            risultati.append({"cig": l["cig"], "url": None, "fonte": "script", "campi": {},
                              "esito": "non_verificabile", "causa": "link_assente",
                              "motivo": "l'avviso non ha un link di gara (documenti_di_gara_link)"})
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
                              "fonte": "script", "campi": {}, "pagina": pag.get("pagina"),
                              "esito": "da_completare", "motivo": pag["problema"]})
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
            codici = set(x["cig"] for x in lotti)
            nella_pagina = cig_nella_pagina(t)
            estranei = [c for c in nella_pagina if c not in codici]
            if estranei:  # la pagina e' leggibile ma e' di un'altra gara: il tool web non serve
                r["campi"]["cig"]["trovato"] = f"{estranei[0]} (diverso)"
                r["campi"]["cig"]["estratto"] = estratto(t, estranei[0])
                r["esito"], r["causa"] = "non_verificabile", "altra_gara"
                r["motivo"] = (f"il link porta a un'altra gara: la pagina riporta il CIG "
                               f"{', '.join(estranei)}, non {l['cig']}")
            elif nella_pagina or any(c.lower() in t.lower() for c in codici):
                r["esito"], r["causa"] = "non_verificabile", "cig_assente"
                r["motivo"] = f"la pagina riporta altri lotti dell'avviso, ma non il CIG {l['cig']}"
            else:  # nessun CIG: forse i dati arrivano via JavaScript, serve il tool web
                r["esito"] = "da_completare"
                r["motivo"] = "la pagina si apre ma non contiene nessun CIG (forse i dati sono caricati via JavaScript)"
        risultati.append(r)

    finale = stampa(id_avviso, risultati, run)
    with open(file_esito, "w", encoding="utf-8") as f:
        json.dump({"idAvviso": id_avviso, "versione": VERSIONE, "esito": finale or "da_completare",
                   "lotti": risultati},
                  f, ensure_ascii=False, indent=2)
    aggiorna_riepilogo(os.path.dirname(run))
    print(f"Risultato salvato in {file_esito.replace(os.sep, '/')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("avviso")
    ap.add_argument("--lotto", help="CIG del lotto verificato col tool web")
    ap.add_argument("--cig", default="")
    ap.add_argument("--importo", default="")
    ap.add_argument("--scadenza", default="")
    ap.add_argument("--oggetto", default="")
    ap.add_argument("--nonraggiungibile", metavar="CIG")
    ap.add_argument("--cigassente", metavar="CIG")
    a = ap.parse_args()
    esegui(a.avviso, None, a.lotto, a.cig, a.importo, a.scadenza, a.oggetto, a.nonraggiungibile,
           a.cigassente)
