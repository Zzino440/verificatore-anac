# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Progetto

"Verifica automatica" per ANAC (DSTech): controlla che il `documenti_di_gara_link` di un avviso porti a una pagina che riporta i campi di ogni lotto previsti per la sua `tipologia` (CIG, importi, date, oggetto, stazione appaltante, aggiudicatari…). Contesto completo (cliente, vincoli, decisioni, persone, glossario) in `ANAC_verifica_automatica_contesto.md`; prossimi passi e cose da chiedere in `TODO.md`.
- Nome ufficiale: "verifica automatica". Mai "AIGIS" né "progetto AI" (richiesta del cliente).
- Vincoli: niente AI esterna, container senza GPU, modello locale piccolo che interviene il meno possibile. La logica deterministica sta nello script; il modello lo chiama e riporta l'output.
- Il documento di contesto descrive anche la skill `verifica-automatica` (v0.3, tre step). È un lavoro precedente e separato: il flusso attivo è quello qui sotto.

## Flusso

Il modello gira in **Unsloth Studio** (tool `python` e `web_search`):
- istruzioni: `prompt-di-sistema.md`, incollato nel System prompt;
- script: il pacchetto `verifica_gara/` in questa cartella, che è la fonte unica del codice e si modifica direttamente;
- nel modello: `import verifica_gara`, con la chat **dentro il progetto** Unsloth che ha questa cartella.

Il prompt ha tre passi: 1 verifica, 2 ripiego web, 3 risposta.

Moduli del pacchetto (solo libreria standard):
| File | Compito |
|---|---|
| `__init__.py` | `VERSIONE`, `esegui_cartella` (batch), `esegui` (un avviso o ripiego web), `_esegui` (orchestrazione dei lotti); `main` per `python -m verifica_gara <cartella o file>` |
| `campi.json` | campi per tipologia (elenco di Matteo): `nome`, `percorso`, `tipo` (codice/importo/data/testo/sino/link), `enable`; `supportata` false per le tipologie senza CIG. Generato una volta, ora si modifica a mano |
| `avviso.py` | lettura dell'avviso: tipologia, lotti, valori dei campi attivi (`risolvi` sui percorsi), ripiego `leggi_per_campi` per JSON rotti |
| `pagina.py` | scaricamento della pagina (`scarica`) e CIG che riporta (`cig_nella_pagina`) |
| `confronti.py` | confronto per tipo di campo (`confronta`), blocchi dei lotti, `valuta` |
| `risposta.py` | riassunto per l'utente (`blocco`, `righe_avviso`, `righe_fallback`), `risposta.md` di dettaglio, cartelle in `esiti/`, `riepilogo.md` |

## Versioni (semver)

La versione sta in **due posti**, sempre uguali:
- `VERSIONE` in `verifica_gara/__init__.py` (è quella che vale);
- ogni `versione="..."` in `prompt-di-sistema.md`.

`esegui` accetta il prompt se coincidono **major e minor**: una patch non obbliga a reincollare il prompt. Con major o minor diverse non dà esito e stampa un errore di versione che dice quale lato è vecchio. `esito.json` riporta la `versione` che l'ha prodotto.

**Procedura automatica (Claude, senza aspettare una richiesta):** ogni volta che modifichi `verifica_gara/` o `prompt-di-sistema.md`, scegli il livello dalla tabella, alza la versione in entrambi i posti **nello stesso commit della modifica** e di' all'utente quale livello hai applicato e perché. Se il livello è dubbio, scegli il più alto tra quelli plausibili e segnalalo. Se il branch ha già alzato la versione di un livello uguale o superiore e non è ancora su `master`, non alzarla di nuovo.

Contratto pubblico: le firme di `esegui_cartella` ed `esegui` usate dal prompt, le righe `FALLBACK_WEB`, il blocco `===== RISPOSTA PER L'UTENTE =====` … `===== FINE =====`, lo schema di `esito.json`, la struttura di `esiti/` (con `risposta.md`) e le colonne di `riepilogo.md`. I `nome` dei campi in `campi.json` sono argomenti del ripiego web: rinominarli è una modifica incompatibile; accendere o spegnere un campo (`enable`) è una patch.

| Modifica | Livello |
|---|---|
| Correzione di un bug, testi del prompt, messaggi di output, refactor senza cambi di comportamento | patch |
| Funzionalità nuova e compatibile (nuovo campo opzionale in `esito.json`, nuovo controllo) | minor |
| Modifica incompatibile: cambia la firma di `esegui` o il modo di chiamarlo dal prompt, lo schema di `esito.json` o di `riepilogo.md` | major |

Finché si è in `0.x` una modifica incompatibile alza la **minor**, non la major: è anche il caso in cui l'utente deve reincollare il prompt. Il passaggio a `1.0.0` si fa solo su richiesta esplicita. Alzare un livello azzera quelli sotto (`0.3.2` → `0.4.0`). Le modifiche che non toccano script né prompt (`CLAUDE.md`, documenti, `avvisi test/`) non alzano niente.

Dopo il commit di una nuova versione, se l'utente lo chiede, crea il tag git `X.Y.Z`. Commit in italiano con i prefissi `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`.

Se cambia major o minor, ricorda all'utente di reincollare `prompt-di-sistema.md` in Unsloth.

## Vincoli di Unsloth (verificati nel suo codice)

Python di Unsloth: `C:/Users/Zzino/.unsloth/studio/unsloth_studio/Scripts/python.exe`. Sorgenti in `.../Lib/site-packages/studio/backend/core/inference/tools.py`.
- Nei tool `USERPROFILE`/`APPDATA` puntano alla cartella di lavoro: mai percorsi assoluti nel prompt.
- `subprocess`, terminale ed `echo` vengono bloccati dal controllo di sicurezza (`_check_code_safety`): il modello deve fare tutto con una chiamata `python` che importa il modulo.
- Il tool `python` (`_python_exec`) scrive il codice in un file `studio_exec_*.py` dentro la cartella di lavoro e lo lancia con `python -u`. Per questo un modulo o un pacchetto nella cartella di lavoro si importa senza percorsi.
- La cartella di lavoro è quella del progetto solo se la chat è in un progetto Unsloth; altrimenti è una sandbox per chat.
- Unsloth aggiunge alle istruzioni del modello l'`AGENTS.md` della cartella del progetto o, se manca o è vuoto, il `CLAUDE.md` (`core/agents_md.py`). Per questo esiste `AGENTS.md` (una riga, non vuoto): senza, il modello legge questo file e copia versioni d'esempio come `0.3.2`.
- Il modello è piccolo e su CPU genera circa 3 token/s: istruzioni brevi e imperative, e il meno testo possibile da scrivere. Con l'avviso incollato ricopiava il JSON (circa 2.300 caratteri per 4 lotti) e il blocco con le tabelle (circa 5.700 caratteri), cioè i circa 15 minuti misurati su Docker. Per questo il flusso normale è il batch: il JSON non passa dal modello, e a schermo esce solo un riassunto. Quando copia male il JSON (parentesi), lo script ripiega su `leggi_per_campi`.

## Come funziona lo script

`esegui_cartella("avvisi_da_verificare", versione=..., [solo="03" | solo=["madrid", "cairo"]])`: tutti i `*.json` della cartella, un avviso per file, oppure con `solo` quelli il cui nome contiene uno dei testi (senza distinguere maiuscole). La cartella contiene i 7 esempi Notion numerati, con gli esiti attesi nel suo `README.md`.
`esegui("<file>", versione=..., [lotto=CIG, <nome campo>="valore", ...] | [cigassente=CIG] | [nonraggiungibile=CIG])`: un avviso incollato (`avviso.json`, file di passaggio) o il ripiego web.
1. `leggi_avviso` legge `tipologia` e prende da `campi.json` i campi con `enable: true`. Una tipologia che non è nel file, o che ha `supportata: false` (senza CIG), dà `ERRORE`. Un campo attivo ma vuoto nell'avviso è `non previsto` (`ok: null` in `esito.json`, `n/p` in tabella) e non pesa sull'esito. `metadata.descrizione` e `titolo` valgono sempre come alternativa alla `descrizione` del lotto.
2. Lo script scarica la pagina con urllib (solo libreria standard) e confronta ogni campo secondo il `tipo`: `codice` è una ricerca esatta senza spazi; `importo` accetta formati IT/EN; `data` vale con l'orario così com'è o convertito in ora italiana (solo la data se l'avviso non ha l'orario); `testo` misura la copertura delle parole (≥ 50%). Un campo con più valori (più SA, più aggiudicatari) è ok solo se li trova tutti.
   - Con più lotti nella stessa pagina, importi e testi del lotto si cercano nel **blocco del lotto**, cioè il pezzo di pagina tra il suo CIG e quello di un altro lotto (`blocchi_lotti`, che sceglie se i dati stanno dopo o prima del CIG). Codici, date e campi dell'avviso si cercano su tutta la pagina.
   - Se manca l'importo principale del lotto (il primo `importo` diretto, `campo_importo`), lo script riporta quello che la pagina indica, ad esempio `€ 95.000,00 (diverso)`, e l'esito è `dubbio` con entrambi i valori nel motivo. Se il blocco non contiene importi, si cerca su tutta la pagina.
3. A schermo esce solo il blocco tra `===== RISPOSTA PER L'UTENTE =====` e `===== FINE =====`: una riga per avviso (id, tipologia, esito) e, per ogni lotto non verificato, "Perché" e "Cosa fare" (`COSA_FARE`). Il batch aggiunge in testa i conteggi e in coda il percorso di `riepilogo.md`. Il dettaglio (pagina con HTTP e titolo, tabella dei campi, estratti della pagina) va in `risposta.md` nella cartella della verifica. Il modello copia il blocco così com'è.
4. Se la pagina è leggibile ma il CIG del lotto manca, lo script decide da solo, senza ripiego web: se la pagina riporta un altro CIG il link porta a un'altra gara (`altra_gara`); se riporta solo altri lotti dell'avviso, `cig_assente`. Il ripiego `FALLBACK_WEB <url> file <file> lotto <CIG> campi <nomi>` resta per errore HTTP o di rete, redirect, pagina quasi vuota/JS e pagina senza nessun CIG. Il modello apre **solo il link dell'avviso** con `web_search(url=...)` (niente ricerca del CIG su altre pagine) e richiama `esegui("<file>", ...)` con `lotto=...` e un argomento per ogni nome della riga (valori copiati), con `cigassente=...` (pagina aperta senza il CIG) o con `nonraggiungibile=...` (pagina che non si apre). Le chiamate di ripiego riportano HTTP, titolo e "Problema dello script" della prima chiamata (`motivo_script`).
5. Esiti per lotto: `verificato`, `dubbio`, `non_verificabile`, più il campo `causa` in `esito.json` (`tutto_trovato`, `campi_diversi`, `altra_gara`, `cig_assente`, `pagina_non_raggiungibile`, `link_assente`). L'esito dell'avviso è quello del lotto peggiore. Senza CIG nella pagina non è mai `verificato`. `esito.json` riporta anche `tipologia`; `riepilogo.md` ha le colonne `tipologia` e `motivo`.

Output su disco:
```
esiti/AAAA-MM-GG/riepilogo.md                       tabella delle verifiche del giorno
esiti/AAAA-MM-GG/NNN_HH-MM-SS_<idAvviso>/avviso.json + esito.json + risposta.md
```
Una nuova verifica crea una cartella con `NNN` progressivo del giorno. Le chiamate di ripiego (`lotto`/`nonraggiungibile`) aggiornano l'ultima cartella dello stesso `idAvviso`.

## Prove

Avvisi di esempio in `avvisi test/`, tutti di tipologia BANDI. Le altre tipologie sono provvisorie finché non arrivano avvisi reali (vedi `TODO.md`).
- MAECI Madrid (`BC515775D3`) → `verificato`;
- visti Cina (`BAABC5642C`) → `verificato`;
- `avviso_maeci_lingue_importo_errato.json`: 4 lotti, l'ultimo con importo volutamente sbagliato (59.000 invece di 95.000) → `dubbio` solo su `B64522444F`;
- `avviso_maeci_link_sbagliato.json`: lotto di Francoforte con il link della gara di Madrid → `non_verificabile` (altra gara, CIG `BC515775D3`) già alla prima chiamata, senza `FALLBACK_WEB`.

Per simulare una chiamata esattamente come la fa Unsloth, eseguila in una cartella di prova nello scratchpad, così non sporchi `esiti/` del progetto:
1. Copia nella cartella di prova `verifica_gara/` e `avvisi_da_verificare/` (oppure, in `avvisi_da_verificare/`, i file di `avvisi test/`).
2. Scrivi lì un `studio_exec_x.py` con il codice del Passo 1 del prompt (`esegui_cartella`).
3. Lancialo con `"<python di Unsloth>" -u studio_exec_x.py`.

Controllo di sicurezza sul codice che il modello scriverà (deve restituire `None`):
```python
from studio.backend.core.inference.tools import _check_code_safety  # con il Python di Unsloth
print(_check_code_safety(codice))
```
