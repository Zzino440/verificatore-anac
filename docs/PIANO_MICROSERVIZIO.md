# Piano: microservizio della verifica automatica

Obiettivo: l'app ANAC (BE Spring) si collega a un solo servizio HTTP, che verifica gli avvisi e restituisce gli esiti. L'app non deve sapere niente di cartelle, prompt, modello o script. Il servizio si avvia con `docker compose up`, sia in locale sia su una VM Azure del cliente (solo CPU).

Stato (2026-11-23): **fasi 1–6 e 8 fatte e provate in locale; fase 7 da eseguire sulla VM** (procedura in `INSTALLAZIONE_VM.md`). Uso del servizio in `README.md`. Dopo le fasi il repo è stato riordinato: il progetto Maven sta nella radice e lo script, con quanto serve a Unsloth, in `src/main/python/`; i percorsi qui sotto sono aggiornati.

## 1. In breve

- **Cosa fa l'app**: manda un avviso (`POST`) e legge l'esito quando è pronto (`GET`). Nient'altro.
- **Cosa fa il servizio**: salva l'avviso, lo mette in coda, fa girare la verifica (con o senza modello) e conserva l'esito.
- **Decisioni prese**:
  - le regole restano nello script Python `verifica_gara/`: il servizio Spring lo lancia come processo, nessun porting in Java;
  - il servizio sta in questo repo, come progetto Maven nella radice (prima nella cartella `servizio/`), con lo script in `src/main/python/`, così script e servizio si versionano insieme.
- **Decisione confermata nelle prove**: in produzione il motore del modello è **llama.cpp server** al posto di Unsloth Studio, e il modello vede un **tool stretto** al posto del tool `python` generico. Motivi:
  - è più leggero e gira senza interfaccia;
  - il modello non può eseguire codice arbitrario.

  Unsloth Studio e `prompt-di-sistema.md` restano per l'uso manuale e le demo.

## 2. Stack consigliato

| Pezzo | Scelta | Perché |
|---|---|---|
| Servizio | Java 21, Spring Boot 3.5.4, Maven | stesso stack del BE ANAC, manutenibile dal team |
| Dipendenze | `spring-boot-starter-web`, `-actuator`, `-validation`, `springdoc-openapi` 2.8.17, Spring AI 1.0.9 (starter OpenAI) | API REST, health, documentazione OpenAPI per l'app; Spring AI gestisce il ciclo delle chiamate ai tool e permette di cambiare motore da configurazione |
| Regole | `verifica_gara/` (Python, solo libreria standard), lanciato come processo | stessi esiti di oggi, una sola fonte delle regole |
| Motore del modello | llama.cpp server, immagine `ghcr.io/ggml-org/llama.cpp:server-b11610` (solo CPU), con il GGUF di **Ministral 3 3B** (2512, Q4_K_M, Apache 2.0) in `modelli/` | leggero, API compatibile OpenAI; il 3B chiama il tool come l'8B, in metà tempo e con 2,3 GB di RAM invece di 3,7 |
| Immagine del servizio | build Maven multi-stage → `eclipse-temurin:21-jre-alpine` + `python3` | immagine snella, come chiesto da ANAC per la sicurezza |
| Avvio | `docker compose` con due servizi, `verifica` e `llm`; solo `verifica` espone una porta | il modello resta nella rete interna |
| Produzione | VM Linux su Azure con Docker | in linea con i requisiti già chiesti al cliente |

## 3. Architettura

```
App ANAC ──HTTP──> verifica (Spring Boot)
                     │
                     ├─ coda a 1 thread (un avviso alla volta: il modello su CPU non regge il parallelo)
                     │
                     ├─ MODALITA=script  ──> python3 -m verifica_gara <file avviso> --json
                     │
                     └─ MODALITA=modello ──> llm (llama.cpp) ⇄ tool verifica_avviso ──> stesso comando
                     │
                     └─ volume dati/:  avvisi/   esiti/AAAA-MM-GG/...
```

- **Tool legato al job.** Il tool non ha argomenti liberi: è il servizio a passare allo script il **percorso del file** dell'avviso in lavorazione. Il modello non può sbagliare avviso, e non si usa la ricerca per numero di `_trova_avviso` (che guarda solo in `avvisi_da_verificare/` e darebbe collisioni tra giorni diversi).
- **L'esito lo legge il servizio** quando il tool esegue lo script, mai dal testo del modello.
- **Due modalità, stessa API.**
  - `script`: meno di un secondo per avviso; serve per sviluppo, test e come piano B.
  - `modello`: circa 1 s in più per avviso (misurato: 7 avvisi in 17 s contro 9 s dello script, con i limiti della VM). La stima di 2 minuti fatta in chat valeva per Unsloth e il tool `python`.
- **Il tool ha `returnDirect`**: il risultato del tool non torna al modello per un riassunto, che il servizio non userebbe. Il modello genera solo la chiamata (circa 9 token).

  L'app non vede la differenza.

## 4. API

È un contratto pubblico: ogni modifica si versiona come `esito.json`.

| Metodo | Percorso | Cosa fa |
|---|---|---|
| `POST` | `/api/verifiche` | body: un avviso JSON o una lista. Risponde `202` con gli id (col modello una chiamata sincrona andrebbe in timeout) |
| `GET` | `/api/verifiche/{id}` | `stato` (`in_coda`, `in_corso`, `fatto`, `errore`) e, quando è `fatto`, il contenuto di `esito.json` |
| `GET` | `/api/verifiche?giorno=AAAA-MM-GG` | le verifiche del giorno |
| `GET` | `/actuator/health`, `/swagger-ui.html` | stato del servizio e documentazione |

- Autenticazione: header `X-API-Key`, con la chiave in una variabile d'ambiente.
- Configurazione, tutta in variabili d'ambiente:
  - `MODALITA` (`script` o `modello`);
  - `LLM_URL`, `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_TIMEOUT`;
  - `API_KEY`;
  - `DATI_DIR`;
  - aggiunte in sviluppo: `PYTHON`, `SCRIPT_DIR`, `SCRIPT_TIMEOUT` (servizio); `PORTA`, `LLM_GGUF`, `COMPOSE_PROFILES` (compose). Elenco completo in `.env.example`.

## 5. Fasi

Ogni fase ha un risultato verificabile. ✅ = fatta e provata.

1. ✅ **Script: uscita JSON.** Aggiungere a `main()` in `src/main/python/verifica_gara/__init__.py` l'opzione `--json`, che stampa il dizionario restituito da `_esegui` al posto del blocco per l'utente.
   - Anche gli errori escono come JSON, con un campo errore e un exit code diverso da 0: oggi sono `SystemExit` di `_trova_avviso`, "nessun lotto" e tipologia ignota in `leggi_avviso`. Il lato Java non deve leggere testo.
   - Opzionale: `--esiti <cartella>`. *Non fatto: il servizio lancia lo script con cartella di lavoro `DATI_DIR`.*
   - Versione minor (0.4.0).
   - *Verifica*: `python -m verifica_gara avvisi_da_verificare/02_madrid_base.json --json` → JSON con l'esito atteso.
2. ✅ **Scheletro Spring** (allora in `servizio/`, oggi nella radice), con quattro package:
   - `api`: controller e DTO;
   - `coda`: executor a 1 thread, stati in memoria;
   - `esecuzione`: `ProcessBuilder` con timeout e cartella di lavoro `DATI_DIR`;
   - `modello`: client del modello e tool.
3. ✅ **Modalità script.** `POST` → file in `dati/avvisi/` → coda → script → stato `fatto` con l'esito. *Da qui l'app può già integrarsi.*
4. ✅ **Modalità modello.**
   - Un prompt corto e nuovo (`src/main/resources/prompt-servizio.md`): "chiama `verifica_avviso`, una sola volta" (niente riassunto: il tool ha `returnDirect`).
   - Client su `LLM_URL`; il tool esegue lo stesso processo della fase 3.
   - Nessun ripiego silenzioso: se il modello non chiama il tool entro il timeout, lo stato diventa `errore` con la causa.
5. ✅ **Docker.**
   - `Dockerfile` multi-stage, che copia `src/main/python/verifica_gara/` e il jar. Utente non root, `TZ=Europe/Rome`, immagine di 291 MB.
   - `docker-compose.yml` nella radice con i servizi `verifica` e `llm`, il volume Docker `dati` (un volume con nome invece di `./dati`, perché un bind mount creato da Docker su Linux appartiene a root e l'utente del container non ci scriverebbe) e `./modelli`.
   - ~~Profilo `solo-script`, che non avvia `llm`~~: i profili di compose possono solo aggiungere servizi, non toglierli. Al suo posto `llm` sta nel profilo `modello`: `docker compose up` avvia solo lo script, `--profile modello` (o `COMPOSE_PROFILES=modello` in `.env`) anche il modello.
6. ✅ **Prova locale.** I 7 avvisi di esempio, con gli esiti attesi in `src/main/python/avvisi_da_verificare/README.md`:
   - prima con il profilo `solo-script`;
   - poi con il modello: esiti identici, tempi annotati.
   - *Fatto il 2026-11-23: 7/7 esiti come da README in tutti e tre i casi. Script 9 s; modello 15 s; modello con `docker-compose.sim-azure.yml` (4 CPU condivise, `llm` 5 GB, `verifica` 1,5 GB) 17 s, RAM `llm` 2,3 GB e `verifica` 0,2 GB.*
7. ⏳ **VM Azure** (procedura pronta in `INSTALLAZIONE_VM.md`; `docker save`/`load` provati in locale, 430 MB).
   - Installare Docker; copiare `docker-compose.yml` e `.env`.
   - Caricare le immagini, dal registry del cliente oppure con `docker save`/`docker load`.
   - Copiare il GGUF in `modelli/` e avviare con `docker compose up -d`.
   - Aprire la porta del servizio solo verso la sottorete del PVL.
   - Misurare tempi e RAM.
8. ✅ **Consegna all'app.** Link OpenAPI, esempio `curl`, `.env.example` (in `README.md`), più la collection Postman in `postman/`.

## 6. Da verificare

- ✅ Compatibilità di Spring AI 1.0.x con Spring Boot 3.5.4: 1.0.9 compila e chiama i tool.
- ✅ Tag dell'immagine llama.cpp e chiamate ai tool con l'opzione `--jinja`: `server-b11610`, tool call corrette.
- ✅ Affidabilità delle chiamate ai tool: con Ministral 3 3B, 7/7 avvisi più 9 chiamate di prova; anche l'8B 3/3. Prove su casi semplici: da tenere d'occhio sui volumi veri.
- ✅ **Licenza del GGUF**: Ministral 3 (2512), sia 3B sia 8B, è Apache 2.0. Da evitare `Ministral-8B-Instruct-2410` (licenza di ricerca).
- ✅ RAM della VM: con il 3B, `llm` 2,3 GB e `verifica` 0,2 GB; 8 GB bastano (provato con i limiti in Docker, non sulla VM).
- Rete in uscita dalla VM verso i portali delle stazioni appaltanti (VPN, firewall).
- Costo giornaliero della macchina: la stima di "alcune decine di euro" non è verificata.

## 7. Domande per Matteo (lato app)

> Risposte proposte in `PIANO_INTEGRAZIONE_CRUSCOTTO.md`: chiama pvl-verifier (job giornaliero o su una giornata scelta), con polling degli id; gli esiti li salva pvl-backend in una collection dedicata.

- Un avviso per chiamata, oppure "verifica la giornata X" e il servizio prende da sé gli avvisi dalle API PVL (fase successiva)?
- L'app controlla lo stato a intervalli (polling) o preferisce una callback a fine verifica?
- L'esito lo salva l'app sul DB (consigliato), con `esiti/` usato solo come log?

## 8. Cosa serve dal cliente

Dalla call del 2026-11-20:
- quale macchina usare;
- un terminale sulla macchina;
- permessi Docker, oppure sudo o un'utenza con privilegi alti;
- accesso Azure almeno in lettura;
- il riferimento di chi gestisce le macchine.
