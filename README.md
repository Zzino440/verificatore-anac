# Verifica automatica

Servizio HTTP (Spring Boot 3.5.4, Java 21) che verifica gli avvisi ANAC: controlla che la pagina del `documenti_di_gara_link` riporti i campi di ogni lotto. Le regole stanno nello script Python `src/main/python/verifica_gara/` (solo libreria standard), che il servizio lancia come processo. Piano e decisioni in `docs/PIANO_MICROSERVIZIO.md`, installazione sulla VM in `docs/INSTALLAZIONE_VM.md`, regole del progetto in `CLAUDE.md`.

## Struttura

```
pom.xml, mvnw, Dockerfile, docker-compose*.yml, .env.example
src/main/java/it/dstech/verifica/   servizio: api, coda, esecuzione (lancio dello script), modello (tool verifica_avviso)
src/main/resources/                 application.properties, prompt-servizio.md (prompt del modello nel servizio)
src/main/python/                    cartella dello script e del progetto Unsloth Studio:
  verifica_gara/                      lo script (fonte unica delle regole)
  avvisi_da_verificare/               7 avvisi di esempio, esiti attesi nel README.md
  prompt-di-sistema.md, AGENTS.md     uso manuale con Unsloth Studio
postman/                            collection ed environment
docs/                               piano, VM, contesto, flusso del prototipo
```

## Avvio

**Da IntelliJ (modalità script):** aprire la cartella come progetto Maven e lanciare la run configuration `VerificaApplication (script)` (in `.run/`): `MODALITA=script`, `API_KEY=locale`, `PYTHON` = Python di Unsloth. Cartella di lavoro: la radice del repo; lo script si prende da `src/main/python` e i dati vanno in `dati/`. Su Windows `PYTHON` deve puntare a un `python.exe` vero: `python`/`python3` nel PATH possono essere shim o lo stub dello Store.

**Da riga di comando:** `./mvnw package`, poi `java -jar target/verifica-servizio-0.1.0.jar` con le stesse variabili d'ambiente.

**Con Docker** (anche la modalità modello), dopo aver copiato `.env.example` in `.env` e impostato `API_KEY`:

```sh
docker compose up -d --build              # servizi secondo COMPOSE_PROFILES/MODALITA di .env
curl -s localhost:8080/actuator/health    # {"status":"UP"}
```

- `MODALITA=script` e `COMPOSE_PROFILES` vuoto: solo regole, meno di un secondo per avviso, senza il servizio `llm`.
- `MODALITA=modello` con `COMPOSE_PROFILES=modello`: avvia anche `llm` (llama.cpp con il GGUF in `modelli/`). Il modello vede solo il tool `verifica_avviso`, legato all'avviso del job; l'esito viene dall'esecuzione del tool.
- Prova con i limiti della VM Azure (4 vCPU, 8 GB): aggiungere `-f docker-compose.yml -f docker-compose.sim-azure.yml`.

**Solo lo script**, senza servizio, da `src/main/python/`: `python -m verifica_gara avvisi_da_verificare` (tutta la cartella) o `python -m verifica_gara <file> --json` (un avviso, uscita JSON).

**Con Unsloth Studio** (uso manuale e demo): il progetto Unsloth deve avere come cartella di lavoro `src/main/python/`; prompt in `src/main/python/prompt-di-sistema.md`.

## API

Autenticazione: header `X-API-Key` con il valore di `API_KEY`. Documentazione: `/swagger-ui.html`, schema OpenAPI in `/v3/api-docs`.

| Metodo | Percorso | Risposta |
|---|---|---|
| `POST` | `/api/verifiche` | body: un avviso JSON o una lista. `202` con `{"ids": [...]}`, nello stesso ordine |
| `GET` | `/api/verifiche/{id}` | `{id, creata, stato, esito, errore}`; `stato`: `in_coda`, `in_corso`, `fatto`, `errore`. Con `fatto`, `esito` è il contenuto di `esito.json`; con `errore`, `errore` ne dà la causa |
| `GET` | `/api/verifiche?giorno=AAAA-MM-GG` | le verifiche del giorno, in ordine di arrivo |
| `GET` | `/actuator/health` | stato del servizio, senza chiave |

Errori: `401` chiave mancante o errata, `400` corpo che non è un avviso o una lista di avvisi, `404` id sconosciuto. Gli stati stanno in memoria e si perdono al riavvio; avvisi ed esiti restano in `DATI_DIR` (volume `dati` in Docker).

```sh
curl -s -X POST localhost:8080/api/verifiche -H "X-API-Key: $API_KEY" \
     -H "Content-Type: application/json" --data-binary @src/main/python/avvisi_da_verificare/02_madrid_base.json
# {"ids":["5f0c..."]}
curl -s localhost:8080/api/verifiche/5f0c... -H "X-API-Key: $API_KEY"
```

## Postman

In `postman/`:
- `verifica.postman_collection.json`: le chiamate di un'app esterna, con controllo del codice HTTP e id salvati tra una richiesta e l'altra (un avviso, una lista, verifiche del giorno, avviso con errore, 401, 400, 404);
- `locale.postman_environment.json`: `baseUrl` e `apiKey`, da compilare (`locale` con la run configuration di IntelliJ, il valore di `.env` con Docker).

Importarli in Postman, scegliere l'environment e lanciare le richieste in ordine (o con il Collection Runner). Le verifiche sono asincrone: ripetere il `GET` dello stato finché è `fatto` o `errore`.
