# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Progetto

"Verifica automatica" per ANAC (DSTech): controlla che il `documenti_di_gara_link` di un avviso porti a una pagina che riporta i campi di ogni lotto previsti per la sua `tipologia` (CIG, importi, date, oggetto, stazione appaltante, aggiudicatari…). Contesto completo (cliente, vincoli, decisioni, persone, glossario) in `docs/ANAC_verifica_automatica_contesto.md`; prossimi passi e cose da chiedere in `TODO.md`.
- Nome ufficiale: "verifica automatica". Mai "AIGIS" né "progetto AI" (richiesta del cliente).
- Vincoli: niente AI esterna, container senza GPU, modello locale piccolo che interviene il meno possibile. **Lo script decide tutto**; il modello fa una sola chiamata `python` e copia il blocco di risposta. Niente ripiego web, niente valori copiati dal modello.
- Il documento di contesto descrive anche la skill `verifica-automatica` (v0.3, tre step). È un lavoro precedente e separato: il flusso attivo è quello qui sotto.

## Flusso

Il modello gira in **Unsloth Studio** (tool `python`):
- istruzioni: `prompt-di-sistema.md`, incollato nel System prompt;
- script: il pacchetto `verifica_gara/` in questa cartella, che è la fonte unica del codice e si modifica direttamente;
- nel modello: `import verifica_gara; verifica_gara.esegui("3")`, con la chat **dentro il progetto** Unsloth che ha questa cartella.

Il prompt ha due passi: 1 verifica, 2 risposta. Regola: **un solo avviso per chat** (sta nel prompt, perché ogni chiamata `python` è un processo nuovo e lo script non vede la chat).

Moduli del pacchetto (solo libreria standard):
| File | Compito |
|---|---|
| `__init__.py` | `VERSIONE`, `esegui` (un avviso, per numero o percorso), `esegui_cartella` (tutta la cartella, solo da riga di comando), `_esegui` (orchestrazione dei lotti); `main` per `python -m verifica_gara <cartella o file>`, con `--json` (un file: stampa il dizionario di `_esegui`; errori come `{"errore": ...}` con exit 1) |
| `campi.json` | campi per tipologia (elenco di Matteo): `nome`, `percorso`, `tipo` (codice/importo/data/testo/sino/link), `enable`; `supportata` false per le tipologie senza CIG. Si modifica a mano |
| `avviso.py` | lettura dell'avviso: tipologia, lotti, valori dei campi attivi (`risolvi` sui percorsi) |
| `pagina.py` | scaricamento della pagina (`scarica`) e CIG che riporta (`cig_nella_pagina`) |
| `confronti.py` | confronto per tipo di campo (`confronta`), blocchi dei lotti, `valuta` |
| `risposta.py` | blocco per l'utente (`blocco`, `righe_avviso`, `COSA_FARE`), cartelle in `esiti/`, `riepilogo.md` |

## Come funziona lo script

1. `esegui("<n>")`: `_trova_avviso` accetta un percorso esistente o il numero del prefisso `NN_` di un file di `avvisi_da_verificare/`. Zero o più corrispondenze → `ERRORE` con l'elenco.
2. `leggi_avviso` prende da `campi.json` i campi con `enable: true` della `tipologia` (tipologia ignota o `supportata: false` → `ERRORE`). Un campo attivo ma vuoto nell'avviso è `non previsto` (`ok: null`) e non pesa. `metadata.descrizione` e `titolo` valgono come alternativa alla `descrizione` del lotto.
3. Lo script scarica la pagina con urllib e confronta ogni campo secondo il `tipo`: `codice` ricerca esatta senza spazi; `importo` formati IT/EN; `data` con l'orario così com'è o in ora italiana (solo la data se l'avviso non ha l'orario); `testo` copertura parole ≥ 50%. Un campo con più valori è ok solo se li trova tutti.
   - Più lotti nella stessa pagina: importi e testi del lotto si cercano nel suo **blocco** (`blocchi_lotti`, tra il suo CIG e quello di un altro lotto); codici, date e campi dell'avviso su tutta la pagina.
   - Importo principale del lotto mancante: lo script riporta quello della pagina, es. `€ 95.000,00 (diverso)`, ed entrambi i valori nel motivo.
4. Esiti per lotto (`causa` in `esito.json`):
   - errore HTTP o di rete → `non_verificabile` (`pagina_non_raggiungibile`); link mancante → `link_assente`;
   - CIG del lotto assente: la pagina riporta un CIG estraneo → `altra_gara`; altrimenti → `cig_assente`;
   - CIG trovato ma un campo manca o è diverso → `dubbio` (`campi_diversi`); tutto trovato → `verificato` (`tutto_trovato`).
   - Redirect e pagina quasi vuota non bloccano l'analisi: la loro `nota` si aggiunge al motivo di ogni esito non verificato.
   - L'esito dell'avviso è quello del lotto peggiore.
5. A schermo esce solo il blocco tra `===== RISPOSTA PER L'UTENTE =====` e `===== FINE =====`: una riga per avviso (id, tipologia, esito), per ogni lotto non verificato "Perché" e "Cosa fare", in coda il percorso di `esito.json` (il batch: conteggi in testa, `riepilogo.md` in coda).

Output su disco:
```
esiti/AAAA-MM-GG/riepilogo.md                       tabella delle verifiche del giorno
esiti/AAAA-MM-GG/NNN_HH-MM-SS_<idAvviso>/esito.json  dettaglio: campi atteso/trovato/ok, estratti, dati della pagina
```

## Servizio (`servizio/`)

Microservizio per l'app ANAC: Java 21, Spring Boot 3.5.4, Spring AI 1.0.9, Maven wrapper. Piano e stato in `docs/PIANO_MICROSERVIZIO.md`, uso e API in `servizio/README.md`, VM in `docs/INSTALLAZIONE_VM.md`. Le regole restano nello script: il servizio lo lancia come processo (`python3 -m verifica_gara avvisi/<id>.json --json`, cartella di lavoro `DATI_DIR`, `PYTHONPATH=SCRIPT_DIR`) e legge `esito.json`.
- API asincrona con `X-API-Key`: `POST /api/verifiche` (avviso o lista) → `202` con gli id; `GET /api/verifiche/{id}` (`in_coda`, `in_corso`, `fatto` con `esito.json`, `errore` con la causa); `GET /api/verifiche?giorno=`. Coda a 1 thread, stati in memoria.
- Package: `api` (controller, filtro della chiave), `coda`, `esecuzione` (`Script`: processo con timeout), `modello` (`Modello`: ChatClient con un solo tool `verifica_avviso`, senza argomenti, legato al job, `returnDirect`; l'esito viene dal tool, mai dal testo; tool non chiamato → `errore`). Prompt in `servizio/src/main/resources/prompt-servizio.md`.
- `MODALITA=script` o `modello`; tutta la configurazione da variabili d'ambiente (`.env.example`).
- Docker: `servizio/Dockerfile` (temurin 21 JRE alpine + python3, non root), `docker-compose.yml` con `verifica` e `llm` (llama.cpp `server-b11610`, profilo `modello`, GGUF Ministral 3 3B in `modelli/`, non versionato), volume `dati`. `docker-compose.sim-azure.yml` simula la VM (4 vCPU, 8 GB).
- Il servizio ha la sua versione nel `pom.xml`; le API e l'uscita di `--json` sono contratto pubblico come `esito.json`.
- In locale: JDK 21 in `~/.jdks/ms-21.0.13.0.2` (non nel PATH), build con `servizio/mvnw`. Da Java `python` può risolvere al Python di MySQL Shell, che non funziona: usare `PYTHON=<python di Unsloth>` o Docker.

## Versioni (semver)

La versione sta solo in `VERSIONE` (`verifica_gara/__init__.py`) ed è scritta in `esito.json`. Il prompt non la passa e non c'è controllo di compatibilità.

**Procedura automatica (Claude, senza aspettare una richiesta):** ogni volta che consegni una modifica a `verifica_gara/` o `prompt-di-sistema.md`, alza `VERSIONE` **prima di chiudere il turno**, anche senza commit, e di' quale livello hai applicato e perché.
- Si confronta con **l'ultima versione consegnata all'utente**; una versione già consegnata non si riusa. Più modifiche nello stesso turno fanno un solo aumento, del livello più alto; se è dubbio, il più alto plausibile.
- Il commit che include le modifiche contiene anche l'aumento di versione.
- **Ogni modifica a `prompt-di-sistema.md` → ricorda all'utente di reincollarlo in Unsloth**: nessun controllo rileva un prompt vecchio.

Contratto pubblico: la firma di `esegui` usata dal prompt, il blocco `===== RISPOSTA PER L'UTENTE =====` … `===== FINE =====`, lo schema di `esito.json`, la struttura di `esiti/` e le colonne di `riepilogo.md`.

| Modifica | Livello |
|---|---|
| Correzione di un bug, testi del prompt, messaggi di output, refactor senza cambi di comportamento, `enable` di un campo | patch |
| Funzionalità nuova e compatibile (nuovo campo opzionale in `esito.json`, nuovo controllo) | minor |
| Modifica incompatibile: firma di `esegui`, schema di `esito.json` o di `riepilogo.md` | major |

Finché si è in `0.x` una modifica incompatibile alza la **minor**. `1.0.0` solo su richiesta esplicita. Alzare un livello azzera quelli sotto. Le modifiche che non toccano script né prompt (`CLAUDE.md`, documenti, avvisi di esempio) non alzano niente. Dopo il commit, se l'utente lo chiede, tag git `X.Y.Z`. Commit in italiano con i prefissi `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`.

## Vincoli di Unsloth (verificati nel suo codice)

Python di Unsloth: `C:/Users/Zzino/.unsloth/studio/unsloth_studio/Scripts/python.exe`. Sorgenti in `.../Lib/site-packages/studio/backend/core/inference/tools.py`.
- Nei tool `USERPROFILE`/`APPDATA` puntano alla cartella di lavoro: mai percorsi assoluti nel prompt.
- `subprocess`, terminale ed `echo` vengono bloccati (`_check_code_safety`): il modello fa tutto con una chiamata `python` che importa il modulo.
- Il tool `python` scrive il codice in `studio_exec_*.py` nella cartella di lavoro e lo lancia con `python -u`: il pacchetto nella cartella si importa senza percorsi.
- La cartella di lavoro è quella del progetto solo se la chat è in un progetto Unsloth; altrimenti è una sandbox per chat.
- Unsloth aggiunge alle istruzioni l'`AGENTS.md` del progetto o, se manca o è vuoto, il `CLAUDE.md` (`core/agents_md.py`). Per questo esiste `AGENTS.md` (una riga, non vuoto).
- Il modello è piccolo e su CPU genera circa 3 token/s: istruzioni brevi e imperative, e il meno testo possibile da scrivere. Per questo indica solo il numero dell'avviso e a schermo esce solo un riassunto.

## Prove

Avvisi di esempio in `avvisi_da_verificare/` (7, tutti BANDI MAECI), con gli esiti attesi nel suo `README.md`. Le tipologie diverse da BANDI sono provvisorie finché non arrivano avvisi reali (vedi `TODO.md`).

Per simulare una chiamata come la fa Unsloth, in una cartella dello scratchpad (così non sporchi `esiti/` del progetto):
1. copia `verifica_gara/` e `avvisi_da_verificare/`;
2. tutta la cartella: `"<python di Unsloth>" -m verifica_gara avvisi_da_verificare`;
3. un avviso: scrivi `studio_exec_x.py` con il codice del Passo 1 (`esegui("<numero>")`) e lancialo con `"<python di Unsloth>" -u studio_exec_x.py`.

Servizio: `docker compose up -d --build` (con `.env`), poi la collection `servizio/postman/` o i `POST` dei 7 avvisi; con il modello `--profile modello`, con i limiti della VM anche `-f docker-compose.sim-azure.yml`. Gli esiti finiscono nel volume `dati`, non in `esiti/` del progetto.

Controllo di sicurezza sul codice che il modello scriverà (deve restituire `None`):
```python
from studio.backend.core.inference.tools import _check_code_safety  # con il Python di Unsloth
print(_check_code_safety(codice))
```
