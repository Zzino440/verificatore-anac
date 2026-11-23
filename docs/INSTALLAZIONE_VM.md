# Installazione sulla VM Azure

Procedura della fase 7 del piano. **Non ancora eseguita**: serve la macchina del cliente (vedi `PIANO_MICROSERVIZIO.md`, sezione 8). I passi 1 e 2 sono stati provati in locale.

## 1. Sul PC di sviluppo: immagini e file da copiare

```sh
docker compose build
docker save verifica-servizio:0.1.0 ghcr.io/ggml-org/llama.cpp:server-b11610 | gzip > immagini.tar.gz   # ~430 MB
```

Da copiare sulla VM, in una cartella (ad esempio `/opt/verifica`):
- `immagini.tar.gz`;
- `docker-compose.yml`;
- `.env`, ricavato da `.env.example` con una `API_KEY` lunga e casuale;
- `modelli/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf` (2 GB, licenza Apache 2.0, da `mistralai/Ministral-3-3B-Instruct-2512-GGUF` su Hugging Face).

Se la VM raggiunge un registry del cliente o `ghcr.io`, al posto di `docker save` si fa `docker push` sul registry e `docker compose pull` sulla VM.

## 2. Sulla VM

1. Installare Docker Engine e il plugin Compose (https://docs.docker.com/engine/install/).
2. Caricare le immagini e avviare:
   ```sh
   cd /opt/verifica
   docker load -i immagini.tar.gz
   docker compose --profile modello up -d    # con MODALITA=modello in .env
   docker compose ps
   curl -s localhost:8080/actuator/health    # {"status":"UP"}
   ```
   Solo script, senza modello: `docker compose up -d` con `MODALITA=script` e `COMPOSE_PROFILES=` vuoto in `.env`.
3. Rete:
   - nel Network Security Group aprire la porta `PORTA` (8080) **solo** verso la sottorete del PVL;
   - controllare che la VM raggiunga in uscita i portali delle stazioni appaltanti (ad esempio `curl -sI https://maeci.traspare.com`).
4. Misure da annotare nel piano:
   - tempo per avviso: `POST` dei 7 avvisi di esempio e tempo fino all'ultimo `fatto`;
   - RAM e CPU: `docker stats --no-stream`.

## 3. Aggiornare

Nuova versione: rifare il passo 1, poi sulla VM `docker load -i immagini.tar.gz && docker compose --profile modello up -d`. Gli esiti restano nel volume `dati`.

## 4. Dove sono i dati

Gli avvisi ricevuti e gli esiti stanno nel volume Docker `dati` (`/dati` nel container):
```sh
docker compose exec verifica ls /dati/esiti
docker compose cp verifica:/dati/esiti ./esiti-copia
```
