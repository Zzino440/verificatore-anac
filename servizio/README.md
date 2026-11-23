# Servizio della verifica automatica

Servizio HTTP (Spring Boot 3.5.4, Java 21) che verifica gli avvisi ANAC con lo script `verifica_gara/` della radice del repo. Piano e decisioni in `../docs/PIANO_MICROSERVIZIO.md`, installazione sulla VM in `../docs/INSTALLAZIONE_VM.md`.

## Avvio

Dalla radice del repo, dopo aver copiato `.env.example` in `.env` e impostato `API_KEY`:

```sh
docker compose up -d --build              # servizi secondo COMPOSE_PROFILES/MODALITA di .env
curl -s localhost:8080/actuator/health    # {"status":"UP"}
```

- `MODALITA=script`: solo regole, meno di un secondo per avviso, senza il servizio `llm`.
- `MODALITA=modello` con `COMPOSE_PROFILES=modello`: avvia anche `llm` (llama.cpp con il GGUF in `modelli/`). Il modello vede solo il tool `verifica_avviso`, legato all'avviso del job; l'esito viene dall'esecuzione del tool.
- Prova con i limiti della VM Azure (4 vCPU, 8 GB): aggiungere `-f docker-compose.yml -f docker-compose.sim-azure.yml`.

Senza Docker, da `servizio/`: `./mvnw package`, poi `java -jar target/verifica-servizio-0.1.0.jar` con `API_KEY`, `PYTHON` (un Python 3 vero) e `DATI_DIR` impostate.

## API

Autenticazione: header `X-API-Key` con il valore di `API_KEY`. Documentazione: `/swagger-ui.html`, schema OpenAPI in `/v3/api-docs`.

| Metodo | Percorso | Risposta |
|---|---|---|
| `POST` | `/api/verifiche` | body: un avviso JSON o una lista. `202` con `{"ids": [...]}`, nello stesso ordine |
| `GET` | `/api/verifiche/{id}` | `{id, creata, stato, esito, errore}`; `stato`: `in_coda`, `in_corso`, `fatto`, `errore`. Con `fatto`, `esito` è il contenuto di `esito.json`; con `errore`, `errore` ne dà la causa |
| `GET` | `/api/verifiche?giorno=AAAA-MM-GG` | le verifiche del giorno, in ordine di arrivo |
| `GET` | `/actuator/health` | stato del servizio, senza chiave |

Errori: `401` chiave mancante o errata, `400` corpo che non è un avviso o una lista di avvisi, `404` id sconosciuto. Gli stati stanno in memoria e si perdono al riavvio; avvisi ed esiti restano nel volume `dati`.

```sh
curl -s -X POST localhost:8080/api/verifiche -H "X-API-Key: $API_KEY" \
     -H "Content-Type: application/json" --data-binary @avvisi_da_verificare/02_madrid_base.json
# {"ids":["5f0c..."]}
curl -s localhost:8080/api/verifiche/5f0c... -H "X-API-Key: $API_KEY"
```

## Postman

In `postman/`:
- `verifica.postman_collection.json`: le chiamate di un'app esterna, con controllo del codice HTTP e id salvati tra una richiesta e l'altra (un avviso, una lista, verifiche del giorno, avviso con errore, 401, 400, 404);
- `locale.postman_environment.json`: `baseUrl` e `apiKey`, da compilare.

Importarli in Postman, scegliere l'environment e lanciare le richieste in ordine (o con il Collection Runner). Le verifiche sono asincrone: ripetere il `GET` dello stato finché è `fatto` o `errore`.
