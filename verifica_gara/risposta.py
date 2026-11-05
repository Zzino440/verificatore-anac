"""Risposta per l'utente (breve a schermo, dettaglio in risposta.md) e salvataggio degli esiti."""
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


def p(path):
    return path.replace(os.sep, "/")


def esito_finale(risultati):
    if any(r["esito"] == "da_completare" for r in risultati):
        return None
    return max((r["esito"] for r in risultati), key=ORDINE.get)


def righe_fallback(file_avviso, risultati):
    """Le righe per il modello: un lotto che lo script non riesce a completare, con i campi da copiare."""
    out = []
    for r in risultati:
        if r["esito"] == "da_completare":
            out.append(f"FALLBACK_WEB {r['url']} file {p(file_avviso)} lotto {r['cig']} "
                       f"campi {', '.join(r['da_copiare'])}")
    return out


def righe_avviso(res):
    """Il riassunto di un avviso: una riga di esito e una riga per ogni lotto non verificato."""
    finale = res["esito"] or "da completare con il tool web (righe FALLBACK_WEB)"
    out = [f"Avviso {res['idAvviso']} ({res['tipologia']}): {finale}"]
    for r in res["lotti"]:
        if r["esito"] in ("verificato", "da_completare"):
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


def dettaglio(id_avviso, tipologia, risultati, finale, run):
    """Il dettaglio per chi controlla: perché, pagina, tabella dei campi ed estratti, cosa fare."""
    out = [f"# Avviso {id_avviso} ({tipologia})", "", f"ESITO FINALE: {finale}"]
    for r in risultati:
        out += ["", f"## Lotto {r['cig']}: {r['esito']}", f"Perché: {r['motivo']}",
                f"Pagina controllata: {r['url'] or '-'}"]
        info = r.get("pagina")
        if info:
            out.append(f"Scaricata dallo script: risposta HTTP {info['http']}, {info['caratteri']} caratteri, "
                       f"titolo \"{info['titolo']}\"")
        if r.get("fonte") == "web":
            if r.get("motivo_script"):
                out.append(f"Problema dello script: {r['motivo_script']}")
            out.append("Ricontrollata dal modello con il tool web")
        if r["campi"]:
            out += ["", "| campo | atteso | trovato | ok |", "|---|---|---|---|"]
            for k, v in r["campi"].items():
                ok = "n/p" if v["ok"] is None else ("si" if v["ok"] else "NO")
                out.append(f"| {k} | {corto(v['atteso'])} | {corto(v['trovato'])} | {ok} |")
            estratti = [(k, v["estratto"]) for k, v in r["campi"].items() if v.get("estratto")]
            if estratti:
                out += ["", "Dove compaiono nella pagina scaricata:"]
                out += [f"- {k}: \"{e}\"" for k, e in estratti]
        if r.get("causa") in COSA_FARE:
            out.append("Cosa fare: " + COSA_FARE[r["causa"]].format(cig=r["cig"]))
    out += ["", "n/p = campo non previsto: vuoto nell'avviso, quindi non controllato."]
    with open(os.path.join(run, "risposta.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


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
