"""Verifica che la pagina del link di gara riporti i campi di ogni lotto di un avviso ANAC
(quelli attivi per la sua tipologia in campi.json). Solo libreria standard.

Uso dal tool python (nella cartella di lavoro), come da prompt-di-sistema.md, un avviso per chat:
  verifica_gara.esegui("3", versione="N")             numero o pezzo del nome di un file di avvisi_da_verificare/
  verifica_gara.esegui("<file>", versione="N", lotto=CIG, <campo>="valore copiato", ...)
  verifica_gara.esegui("<file>", versione="N", cigassente=CIG)
  verifica_gara.esegui("<file>", versione="N", nonraggiungibile=CIG)
Da riga di comando: python -m verifica_gara <cartella o file .json>
Ogni verifica va in esiti/AAAA-MM-GG/NNN_HH-MM-SS_<idAvviso>/ (avviso.json, esito.json, risposta.md),
con esiti/AAAA-MM-GG/riepilogo.md che elenca le verifiche del giorno.
"""
import argparse
import glob
import json
import os
import re
import shutil
import sys

from .avviso import leggi_avviso
from .confronti import IMPORTO_RX, blocchi_lotti, estratto, importo_della_pagina, valuta
from .pagina import cig_nella_pagina, scarica
from .risposta import (aggiorna_riepilogo, blocco, cartella_run, dettaglio, esito_finale, p,
                       righe_avviso, righe_fallback)

sys.stdout.reconfigure(encoding="utf-8")

VERSIONE = "0.2.0"  # semver, uguale a versione="..." in prompt-di-sistema.md


def _semver(v):
    """'0.1.2' -> (0, 1, 2); None se non e' una versione semver."""
    parti = str(v).split(".")
    return tuple(int(p) for p in parti) if len(parti) == 3 and all(p.isdigit() for p in parti) else None


def _versione_ok(versione):
    """Prompt e modulo sono compatibili se coincidono major e minor: una patch non obbliga a
    reincollare il prompt."""
    chiesta, mia = _semver(versione), _semver(VERSIONE)
    if versione is None or (chiesta is not None and chiesta[:2] == mia[:2]):
        return True
    if chiesta is None or chiesta[:2] < mia[:2]:
        vecchio = "le istruzioni sono vecchie"
        rimedio = "reincollare prompt-di-sistema.md nel System prompt e aprire una nuova chat nel progetto"
    else:
        vecchio = f"il modulo {__name__} e' vecchio"
        rimedio = "ricopiare la cartella verifica_gara nella cartella del progetto"
    print(f"ERRORE di versione: le istruzioni chiedono la versione {versione}, il modulo {__name__} "
          f"e' la {VERSIONE}, quindi {vecchio}. Di' all'utente di {rimedio}.")
    return False


CARTELLA_AVVISI = "avvisi_da_verificare"


def _trova_avviso(rif):
    """Il file dell'avviso: rif e' un percorso esistente, il numero del file ("3", "03") o un pezzo
    del suo nome in avvisi_da_verificare/. Deve corrispondere a un solo file."""
    if os.path.isfile(rif):
        return rif
    tutti = sorted(glob.glob(os.path.join(CARTELLA_AVVISI, "*.json")))
    nomi = [os.path.basename(f) for f in tutti]
    r = str(rif).strip().lower()
    if r.isdigit():
        presi = [f for f, n in zip(tutti, nomi) if re.match(r"\d+_", n) and int(n.split("_")[0]) == int(r)]
    else:
        r = re.sub(r"[\s-]+", "_", r)
        presi = [f for f, n in zip(tutti, nomi) if r in n.lower()]
    if not presi:
        sys.exit(f"ERRORE: nessun avviso corrisponde a {rif!r}. Avvisi disponibili: " + ", ".join(nomi))
    if len(presi) > 1:
        sys.exit(f"ERRORE: {rif!r} corrisponde a più avvisi ("
                 + ", ".join(os.path.basename(f) for f in presi) + "): indicane uno solo.")
    return presi[0]


def esegui(avviso="avviso.json", versione=None, lotto=None, nonraggiungibile=None, cigassente=None,
           **valori):
    """Un solo avviso: un percorso, oppure il numero o un pezzo del nome di un file di
    avvisi_da_verificare/. Nel ripiego web (lotto=CIG) gli altri argomenti sono i campi copiati
    dalla pagina, con i nomi della riga FALLBACK_WEB."""
    if not _versione_ok(versione):
        return
    try:
        avviso = _trova_avviso(avviso)
        res = _esegui(avviso, lotto, valori, nonraggiungibile, cigassente)
    except SystemExit as e:  # gli errori previsti escono con un messaggio, non con un traceback
        print(e)
        return
    fallback = righe_fallback(avviso, res["lotti"])
    if fallback:
        print("AZIONE RICHIESTA: usa il tool web come indicato al passo 2 delle istruzioni per questi lotti:")
        print("\n".join(fallback))
        return
    blocco(righe_avviso(res) + [f"Dettaglio con tabelle ed estratti: {p(res['run'])}/risposta.md"])


def esegui_cartella(cartella=CARTELLA_AVVISI, versione=None):
    """Tutti i file .json della cartella, uno per avviso (riga di comando, non dal modello).
    A schermo solo il riassunto e le righe FALLBACK_WEB; il dettaglio va nel risposta.md di ciascuno."""
    if not _versione_ok(versione):
        return
    files = sorted(glob.glob(os.path.join(cartella, "*.json")))
    if not files:
        print(f"ERRORE: nessun file .json nella cartella {cartella} (cartella di lavoro {os.getcwd()}).")
        return
    righe, fallback, conta, giorno = [], [], {}, None
    for f in files:
        try:
            res = _esegui(f, None, {}, None, None)
        except SystemExit as e:
            righe.append(f"File {p(f)}: {e}")
            conta["errori"] = conta.get("errori", 0) + 1
            continue
        giorno = os.path.dirname(res["run"])
        stato = res["esito"] or "da completare"
        conta[stato] = conta.get(stato, 0) + 1
        righe += righe_avviso(res)
        fallback += righe_fallback(f, res["lotti"])
    if fallback:
        print("AZIONE RICHIESTA: usa il tool web come indicato al passo 2 delle istruzioni per questi lotti:")
        print("\n".join(fallback))
    testa = f"Avvisi controllati: {len(files)} ({', '.join(f'{k} {v}' for k, v in conta.items())})"
    coda = [f"Riepilogo del giorno: {p(giorno)}/riepilogo.md"] if giorno else []
    blocco([testa] + righe + coda)


def _esegui(avviso, lotto, valori_web, nonraggiungibile, cigassente):
    id_avviso, tipologia, lotti = leggi_avviso(avviso)
    if not lotti:
        sys.exit("ERRORE: nessun lotto trovato nell'avviso (sections -> items con tipo_oggetto 'lotto').")

    bersaglio = lotto or nonraggiungibile or cigassente
    if bersaglio and bersaglio not in {l["cig"] for l in lotti}:
        sys.exit(f"ERRORE: CIG {bersaglio} non presente nell'avviso. CIG validi: "
                 + ", ".join(l["cig"] for l in lotti))
    if lotto:
        noti = {c["nome"] for c in lotti[0]["campi"]}
        ignoti = [k for k in valori_web if k not in noti]
        if ignoti:
            print(f"NOTA: campi ignorati perché non previsti per {tipologia}: {', '.join(ignoti)}")

    run = cartella_run(id_avviso, nuova=not bersaglio)
    if not bersaglio:
        shutil.copyfile(avviso, os.path.join(run, "avviso.json"))
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
            r = valuta(l, valori_web, "web")
            r["pagina"], r["motivo_script"] = prima.get("pagina"), motivo_script
            risultati.append(r)
            continue
        if not l["url"]:
            risultati.append({"cig": l["cig"], "url": None, "fonte": "script", "campi": {},
                              "esito": "non_verificabile", "causa": "link_assente",
                              "motivo": "l'avviso non ha un link di gara (documenti_di_gara_link)"})
            continue
        if l["url"] not in cache:
            cache[l["url"]] = scarica(l["url"])
        pag = cache[l["url"]]
        # i campi che il modello deve copiare dalla pagina se serve il ripiego web
        da_copiare = [c["nome"] for c in l["campi"] if l["valori"][c["nome"]]]
        if pag.get("problema"):
            risultati.append({"cig": l["cig"], "url": l["url"], "url_finale": pag.get("url_finale"),
                              "fonte": "script", "campi": {}, "pagina": pag.get("pagina"),
                              "esito": "da_completare", "motivo": pag["problema"], "da_copiare": da_copiare})
            continue
        t = pag["testo"]
        if "blocchi" not in pag:
            pag["blocchi"] = blocchi_lotti(t, [x for x in lotti if x["url"] == l["url"]])
        bl = pag["blocchi"].get(l["cig"])
        t_imp = bl if bl and re.search(IMPORTO_RX, bl, re.I) else t
        r = valuta(l, {"pagina": t, "blocco": bl}, "script", pag["url_finale"],
                   importo_della_pagina(t_imp, blocco=t_imp is bl))
        r["pagina"] = pag["pagina"]
        if "cig" in r["campi"] and not r["campi"]["cig"]["ok"]:
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
                r["esito"], r["da_copiare"] = "da_completare", da_copiare
                r["motivo"] = "la pagina si apre ma non contiene nessun CIG (forse i dati sono caricati via JavaScript)"
        risultati.append(r)

    finale = esito_finale(risultati)
    with open(file_esito, "w", encoding="utf-8") as f:
        json.dump({"idAvviso": id_avviso, "tipologia": tipologia, "versione": VERSIONE,
                   "esito": finale or "da_completare", "lotti": risultati},
                  f, ensure_ascii=False, indent=2)
    if finale:
        dettaglio(id_avviso, tipologia, risultati, finale, run)
    aggiorna_riepilogo(os.path.dirname(run))
    return {"idAvviso": id_avviso, "tipologia": tipologia, "esito": finale, "lotti": risultati, "run": run}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("percorso", help="cartella con gli avvisi .json oppure un solo file .json")
    a = ap.parse_args()
    if os.path.isdir(a.percorso):
        esegui_cartella(a.percorso)
    else:
        esegui(a.percorso)
