# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Progetto

"Verifica automatica" per ANAC (DSTech): controlla che il `documenti_di_gara_link` di un avviso porti a una pagina che riporta CIG, importo, scadenza e oggetto di ogni lotto. Contesto completo (cliente, vincoli, decisioni, persone, glossario) in `ANAC_verifica_automatica_contesto.md`.
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
| `__init__.py` | `VERSIONE`, `esegui` (controllo versione) e `_esegui` (orchestrazione dei lotti, ripiego web); `main` per `python -m verifica_gara` |
| `avviso.py` | lettura dell'avviso e dei lotti, con ripiego `leggi_per_campi` per JSON rotti |
| `pagina.py` | scaricamento della pagina (`scarica`) e CIG che riporta (`cig_nella_pagina`) |
| `confronti.py` | confronto dei campi: importo, scadenza, oggetto, blocchi dei lotti, `valuta` |
| `risposta.py` | blocco per l'utente (`stampa`), cartelle in `esiti/`, `riepilogo.md` |

## Versioni (semver)

La versione sta in **due posti**, sempre uguali:
- `VERSIONE` in `verifica_gara/__init__.py` (è quella che vale);
- ogni `versione="..."` in `prompt-di-sistema.md`.

`esegui` accetta il prompt se coincidono **major e minor**: una patch non obbliga a reincollare il prompt. Con major o minor diverse non dà esito e stampa un errore di versione che dice quale lato è vecchio. `esito.json` riporta la `versione` che l'ha prodotto.

**Procedura automatica (Claude, senza aspettare una richiesta):** ogni volta che modifichi `verifica_gara/` o `prompt-di-sistema.md`, scegli il livello dalla tabella, alza la versione in entrambi i posti **nello stesso commit della modifica** e di' all'utente quale livello hai applicato e perché. Se il livello è dubbio, scegli il più alto tra quelli plausibili e segnalalo. Se il branch ha già alzato la versione di un livello uguale o superiore e non è ancora su `master`, non alzarla di nuovo.

Contratto pubblico: la firma di `esegui` usata dal prompt, le righe `FALLBACK_WEB`, il blocco `===== RISPOSTA PER L'UTENTE =====` … `===== FINE =====`, lo schema di `esito.json`, la struttura di `esiti/` e le colonne di `riepilogo.md`.

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
- Il modello è piccolo: istruzioni brevi e imperative, una sola chiamata `python` per avviso. Copia spesso male il JSON (parentesi): lo script ripiega su `leggi_per_campi`, che legge i valori campo per campo.

## Come funziona lo script

`esegui("avviso.json", versione=..., [lotto=CIG, cig, importo, scadenza, oggetto] | [cigassente=CIG] | [nonraggiungibile=CIG])`
1. Il modello scrive il JSON incollato in `avviso.json` nella cartella di lavoro (file di passaggio, sovrascritto ogni volta) e chiama `esegui`.
2. Lo script scarica la pagina con urllib (solo libreria standard) e confronta i campi: importo in formati IT/EN, scadenza con orario così com'è o convertito in ora italiana, oggetto per copertura delle parole.
   - Con più lotti nella stessa pagina, importo e oggetto si cercano nel **blocco del lotto**, cioè il pezzo di pagina tra il suo CIG e quello di un altro lotto (`blocchi_lotti`, che sceglie se i dati stanno dopo o prima del CIG). CIG e scadenza si cercano su tutta la pagina.
   - Se l'importo atteso manca, lo script riporta quello che la pagina indica per il lotto, ad esempio `€ 95.000,00 (diverso)`, e l'esito è `dubbio` con entrambi i valori nel motivo. Se il blocco non contiene importi, si cerca su tutta la pagina.
3. A fine verifica stampa un blocco tra `===== RISPOSTA PER L'UTENTE =====` e `===== FINE =====`: esito finale e, per ogni lotto, "Perché" (il motivo in italiano semplice), pagina controllata con HTTP e titolo, tabella dei campi con gli estratti della pagina, "Cosa fare" (frase fissa per causa, `COSA_FARE`). Il modello copia il blocco così com'è e può aggiungere un breve commento pertinente, senza contraddire esito e motivo.
4. Se la pagina è leggibile ma il CIG del lotto manca, lo script decide da solo, senza ripiego web: se la pagina riporta un altro CIG il link porta a un'altra gara (`altra_gara`); se riporta solo altri lotti dell'avviso, `cig_assente`. Il ripiego `FALLBACK_WEB <url> lotto <CIG>` resta per errore HTTP o di rete, redirect, pagina quasi vuota/JS e pagina senza nessun CIG. Il modello apre **solo il link dell'avviso** con `web_search(url=...)` (niente ricerca del CIG su altre pagine) e richiama `esegui` con `lotto=...` (valori copiati), `cigassente=...` (pagina aperta senza il CIG) o `nonraggiungibile=...` (pagina che non si apre). Le chiamate di ripiego riportano HTTP, titolo e "Problema dello script" della prima chiamata (`motivo_script`).
5. Esiti per lotto: `verificato`, `dubbio`, `non_verificabile`, più il campo `causa` in `esito.json` (`tutto_trovato`, `campi_diversi`, `altra_gara`, `cig_assente`, `pagina_non_raggiungibile`, `link_assente`). L'esito dell'avviso è quello del lotto peggiore. Senza CIG nella pagina non è mai `verificato`. `riepilogo.md` ha anche la colonna `motivo`.

Output su disco:
```
esiti/AAAA-MM-GG/riepilogo.md                       tabella delle verifiche del giorno
esiti/AAAA-MM-GG/NNN_HH-MM-SS_<idAvviso>/avviso.json + esito.json
```
Una nuova verifica crea una cartella con `NNN` progressivo del giorno. Le chiamate di ripiego (`lotto`/`nonraggiungibile`) aggiornano l'ultima cartella dello stesso `idAvviso`.

## Prove

Avvisi di esempio in `avvisi test/`:
- MAECI Madrid (`BC515775D3`) → `verificato`;
- visti Cina (`BAABC5642C`) → `verificato`;
- `avviso_maeci_lingue_importo_errato.json`: 4 lotti, l'ultimo con importo volutamente sbagliato (59.000 invece di 95.000) → `dubbio` solo su `B64522444F`;
- `avviso_maeci_link_sbagliato.json`: lotto di Francoforte con il link della gara di Madrid → `non_verificabile` (altra gara, CIG `BC515775D3`) già alla prima chiamata, senza `FALLBACK_WEB`.

Per simulare una chiamata esattamente come la fa Unsloth, eseguila in una cartella di prova nello scratchpad, così non sporchi `esiti/` del progetto:
1. Copia la cartella `verifica_gara/` nella cartella di prova.
2. Scrivi lì un `studio_exec_x.py` con il codice del Passo 1 del prompt.
3. Lancialo con `"<python di Unsloth>" -u studio_exec_x.py`.

Controllo di sicurezza sul codice che il modello scriverà (deve restituire `None`):
```python
from studio.backend.core.inference.tools import _check_code_safety  # con il Python di Unsloth
print(_check_code_safety(codice))
```
