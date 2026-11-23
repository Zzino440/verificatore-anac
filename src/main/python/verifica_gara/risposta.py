"""Risposta per l'utente (breve a schermo) e salvataggio degli esiti."""
import json
import os
import re
from datetime import datetime

CARTELLA_ESITI = "esiti"

ORDINE = {"verificato": 0, "dubbio": 1, "non_verificabile": 2}
# cosa deve fare chi legge l'esito, per ogni causa ({cig} = CIG del lotto)
COSA_FARE = {
    "link_assente": "inserire documenti_di_gara_link nell'avviso.",
    "pagina_non_raggiungibile": "controllare che il link sia giusto e che il sito sia online, poi rifare la verifica.",
    "altra_gara": "correggere documenti_di_gara_link: deve portare alla pagina della gara con CIG {cig}.",
    "cig_assente": "controllare che il link porti alla gara giusta e che la pagina riporti il CIG {cig}.",
    "campi_diversi": "controllare i campi segnati NO: va corretto l'avviso oppure la pagina di gara.",
}


def p(path):
    return path.replace(os.sep, "/")


def esito_finale(risultati):
    return max((r["esito"] for r in risultati), key=ORDINE.get)


def righe_avviso(res):
    """Il riassunto di un avviso: una riga di esito e una riga per ogni lotto non verificato."""
    out = [f"Avviso {res['idAvviso']} ({res['tipologia']}): {res['esito']}"]
    for r in res["lotti"]:
        if r["esito"] == "verificato":
            continue
        riga = f"- lotto {r['cig']}: {r['esito']}. Perché: {r['motivo']}."
        if r.get("causa") in COSA_FARE:
            riga += " Cosa fare: " + COSA_FARE[r["causa"]].format(cig=r["cig"])
        out.append(riga)
    return out


def blocco(righe):
    print("\n===== RISPOSTA PER L'UTENTE =====")
    print("\n".join(righe))
    print("===== FINE =====")


def cartella_run(id_avviso):
    """esiti/AAAA-MM-GG/NNN_HH-MM-SS_<idAvviso>, con NNN progressivo del giorno."""
    nome = re.sub(r"[^\w.-]", "_", str(id_avviso or "avviso"))
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
             "| n. | ora | avviso | tipologia | esito | motivo | cartella |", "|---|---|---|---|---|---|---|"]
    for nome in sorted(os.listdir(giorno)):
        f_esito = os.path.join(giorno, nome, "esito.json")
        if os.path.isfile(f_esito):
            with open(f_esito, encoding="utf-8") as f:
                e = json.load(f)
            lotti = e.get("lotti") or []
            peggiore = max(lotti, key=lambda r: ORDINE.get(r.get("esito"), 3), default={})
            motivo = str(peggiore.get("motivo", "")).replace("|", "/")
            righe.append(f"| {nome[:3]} | {nome[4:12].replace('-', ':')} | {e.get('idAvviso')} | "
                         f"{e.get('tipologia', '-')} | {e.get('esito')} | {motivo} | {nome} |")
    with open(os.path.join(giorno, "riepilogo.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(righe) + "\n")
