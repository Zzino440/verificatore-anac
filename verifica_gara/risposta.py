"""Blocco di risposta per l'utente e salvataggio degli esiti su disco."""
import glob
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


def corto(v, n=55):
    s = "-" if v is None else str(v)
    return s if len(s) <= n else s[:n] + "..."


def stampa(id_avviso, risultati, run):
    aperti = [r for r in risultati if r["esito"] == "da_completare"]
    if aperti:
        print(f"\nAvviso {id_avviso}: lo script non riesce a completare la verifica di questi lotti:")
        for r in aperti:
            print(f"- lotto {r['cig']}: {r['motivo']}")
        print("\nAZIONE RICHIESTA: usa il tool web come indicato al passo 2 delle istruzioni per questi lotti:")
        for r in aperti:
            print(f"FALLBACK_WEB {r['url']} lotto {r['cig']}")
        return None
    finale = max((r["esito"] for r in risultati), key=ORDINE.get)
    print("\n===== RISPOSTA PER L'UTENTE =====")
    print(f"Avviso {id_avviso}")
    print(f"ESITO FINALE: {finale}")
    for r in risultati:
        print(f"\nLotto {r['cig']}: {r['esito']}")
        print(f"  Perché: {r['motivo']}")
        print(f"  Pagina controllata: {r['url'] or '-'}")
        info = r.get("pagina")
        if info:
            print(f"  Scaricata dallo script: risposta HTTP {info['http']}, {info['caratteri']} caratteri, "
                  f"titolo \"{info['titolo']}\"")
        if r.get("fonte") == "web":
            if r.get("motivo_script"):
                print(f"  Problema dello script: {r['motivo_script']}")
            print("  Ricontrollata dal modello con il tool web")
        if r["campi"]:
            print("  | campo | atteso | trovato | ok |\n  |---|---|---|---|")
            for k, v in r["campi"].items():
                print(f"  | {k} | {corto(v['atteso'])} | {corto(v['trovato'])} | {'si' if v['ok'] else 'NO'} |")
            estratti = [(k, v["estratto"]) for k, v in r["campi"].items() if v.get("estratto")]
            if estratti:
                print("  Dove compaiono nella pagina scaricata:")
                for k, e in estratti:
                    print(f"  - {k}: \"{e}\"")
        if r.get("causa") in COSA_FARE:
            print("  Cosa fare: " + COSA_FARE[r["causa"]].format(cig=r["cig"]))
    print(f"\nCartella della verifica: {run.replace(os.sep, '/')} (avviso.json ed esito.json)")
    print("===== FINE =====")
    return finale


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
             "| n. | ora | avviso | esito | motivo | cartella |", "|---|---|---|---|---|---|"]
    for nome in sorted(os.listdir(giorno)):
        p = os.path.join(giorno, nome, "esito.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                e = json.load(f)
            lotti = e.get("lotti") or []
            peggiore = max(lotti, key=lambda r: ORDINE.get(r.get("esito"), 3), default={})
            motivo = str(peggiore.get("motivo", "")).replace("|", "/")
            righe.append(f"| {nome[:3]} | {nome[4:12].replace('-', ':')} | {e.get('idAvviso')} | "
                         f"{e.get('esito')} | {motivo} | {nome} |")
    with open(os.path.join(giorno, "riepilogo.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(righe) + "\n")
