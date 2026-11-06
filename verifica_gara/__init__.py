"""Verifica che la pagina del link di gara riporti i campi di ogni lotto di un avviso ANAC
(quelli attivi per la sua tipologia in campi.json). Solo libreria standard.

Uso dal tool python (nella cartella di lavoro), come da prompt-di-sistema.md, un avviso per chat:
  verifica_gara.esegui("3")       numero del file in avvisi_da_verificare/ (o percorso del file)
Da riga di comando: python -m verifica_gara <cartella o file .json>
Ogni verifica va in esiti/AAAA-MM-GG/NNN_HH-MM-SS_<idAvviso>/esito.json,
con esiti/AAAA-MM-GG/riepilogo.md che elenca le verifiche del giorno.
"""
import argparse
import glob
import json
import os
import re
import sys

from .avviso import leggi_avviso
from .confronti import IMPORTO_RX, blocchi_lotti, estratto, importo_della_pagina, valuta
from .pagina import cig_nella_pagina, scarica
from .risposta import aggiorna_riepilogo, blocco, cartella_run, esito_finale, p, righe_avviso

sys.stdout.reconfigure(encoding="utf-8")

VERSIONE = "0.3.0"  # semver, scritta in esito.json

CARTELLA_AVVISI = "avvisi_da_verificare"


def _trova_avviso(rif):
    """Il file dell'avviso: rif e' un percorso esistente o il numero del file ("3", "03") in
    avvisi_da_verificare/. Deve corrispondere a un solo file."""
    if os.path.isfile(rif):
        return rif
    tutti = sorted(glob.glob(os.path.join(CARTELLA_AVVISI, "*.json")))
    nomi = [os.path.basename(f) for f in tutti]
    r = str(rif).strip()
    presi = [f for f, n in zip(tutti, nomi)
             if r.isdigit() and re.match(r"\d+_", n) and int(n.split("_")[0]) == int(r)]
    if not presi:
        sys.exit(f"ERRORE: nessun avviso corrisponde a {rif!r}. Avvisi disponibili: " + ", ".join(nomi))
    if len(presi) > 1:
        sys.exit(f"ERRORE: {rif!r} corrisponde a più avvisi ("
                 + ", ".join(os.path.basename(f) for f in presi) + "): indicane uno solo.")
    return presi[0]


def esegui(avviso):
    """Un solo avviso: il numero del file in avvisi_da_verificare/ o un percorso."""
    try:
        res = _esegui(_trova_avviso(avviso))
    except SystemExit as e:  # gli errori previsti escono con un messaggio, non con un traceback
        print(e)
        return
    blocco(righe_avviso(res) + [f"Dettaglio: {p(res['run'])}/esito.json"])


def esegui_cartella(cartella=CARTELLA_AVVISI):
    """Tutti i file .json della cartella, uno per avviso (riga di comando, non dal modello)."""
    files = sorted(glob.glob(os.path.join(cartella, "*.json")))
    if not files:
        print(f"ERRORE: nessun file .json nella cartella {cartella} (cartella di lavoro {os.getcwd()}).")
        return
    righe, conta, giorno = [], {}, None
    for f in files:
        try:
            res = _esegui(f)
        except SystemExit as e:
            righe.append(f"File {p(f)}: {e}")
            conta["errori"] = conta.get("errori", 0) + 1
            continue
        giorno = os.path.dirname(res["run"])
        conta[res["esito"]] = conta.get(res["esito"], 0) + 1
        righe += righe_avviso(res)
    testa = f"Avvisi controllati: {len(files)} ({', '.join(f'{k} {v}' for k, v in conta.items())})"
    coda = [f"Riepilogo del giorno: {p(giorno)}/riepilogo.md"] if giorno else []
    blocco([testa] + righe + coda)


def _esegui(avviso):
    id_avviso, tipologia, lotti = leggi_avviso(avviso)
    if not lotti:
        sys.exit("ERRORE: nessun lotto trovato nell'avviso (sections -> items con tipo_oggetto 'lotto').")

    cache, risultati = {}, []
    for l in lotti:
        if not l["url"]:
            risultati.append({"cig": l["cig"], "url": None, "campi": {},
                              "esito": "non_verificabile", "causa": "link_assente",
                              "motivo": "l'avviso non ha un link di gara (documenti_di_gara_link)"})
            continue
        if l["url"] not in cache:
            cache[l["url"]] = scarica(l["url"])
        pag = cache[l["url"]]
        if pag.get("problema"):
            risultati.append({"cig": l["cig"], "url": l["url"], "campi": {},
                              "esito": "non_verificabile", "causa": "pagina_non_raggiungibile",
                              "motivo": pag["problema"]})
            continue
        t = pag["testo"]
        if "blocchi" not in pag:
            pag["blocchi"] = blocchi_lotti(t, [x for x in lotti if x["url"] == l["url"]])
        bl = pag["blocchi"].get(l["cig"])
        t_imp = bl if bl and re.search(IMPORTO_RX, bl, re.I) else t
        r = valuta(l, t, bl, pag["url_finale"], importo_della_pagina(t_imp, blocco=t_imp is bl))
        r["pagina"] = pag["pagina"]
        if "cig" in r["campi"] and not r["campi"]["cig"]["ok"]:
            codici = set(x["cig"] for x in lotti)
            nella_pagina = cig_nella_pagina(t)
            estranei = [c for c in nella_pagina if c not in codici]
            if estranei:  # la pagina e' leggibile ma e' di un'altra gara
                r["campi"]["cig"]["trovato"] = f"{estranei[0]} (diverso)"
                r["campi"]["cig"]["estratto"] = estratto(t, estranei[0])
                r["esito"], r["causa"] = "non_verificabile", "altra_gara"
                r["motivo"] = (f"il link porta a un'altra gara: la pagina riporta il CIG "
                               f"{', '.join(estranei)}, non {l['cig']}")
            elif nella_pagina or any(c.lower() in t.lower() for c in codici):
                r["motivo"] = f"la pagina riporta altri lotti dell'avviso, ma non il CIG {l['cig']}"
            else:
                r["motivo"] = f"la pagina non riporta nessun CIG, quindi nemmeno {l['cig']}"
        if r["esito"] != "verificato" and pag.get("nota"):
            r["motivo"] += f" ({pag['nota']})"
        risultati.append(r)

    finale = esito_finale(risultati)
    run = cartella_run(id_avviso)
    with open(os.path.join(run, "esito.json"), "w", encoding="utf-8") as f:
        json.dump({"idAvviso": id_avviso, "tipologia": tipologia, "versione": VERSIONE,
                   "esito": finale, "lotti": risultati},
                  f, ensure_ascii=False, indent=2)
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
