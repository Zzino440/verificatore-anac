# Flusso del prototipo: verifica automatica su macchina o Docker

Obiettivo: verificare ogni giorno gli avvisi (100–200, solo non scaduti) senza aprire le chat di Unsloth a mano, con **un avviso per sessione del modello**.

Stato: **superato dal servizio** (nella radice del repo, vedi `PIANO_MICROSERVIZIO.md` e `README.md`). Il lanciatore è diventato il servizio HTTP: riceve gli avvisi, li mette in coda e li verifica uno alla volta, con llama.cpp al posto di Unsloth Studio e il tool `verifica_avviso` al posto del tool `python`. Unsloth Studio resta per l'uso manuale e le demo. Il resto del documento descrive l'idea di partenza con Unsloth, mai provata con chiamate reali.

## Cosa offre Unsloth Studio

Verificato nei sorgenti di `studio/backend` della versione installata, non nella documentazione online.

- **API compatibile con OpenAI**: `POST /v1/chat/completions` (`routes/inference.py`). Si mandano i messaggi system (il prompt) e user ("verifica il 03"), più alcuni campi propri di Unsloth:
  - `enable_tools: true` ed `enabled_tools: ["python"]`: il tool gira **sul server**, come nella chat (una chiamata `python`), tutto in una sola richiesta;
  - `session_id: "project-<id progetto>"`: le chiamate `python` girano nella **cartella del progetto**, dove stanno `verifica_gara/` e `avvisi_da_verificare/` (oggi `src/main/python/`) (`_project_workdir_for` in `core/inference/tools.py`).
- **Permessi**:
  - senza `permission_mode` esplicito, una richiesta non in streaming non chiede conferme ed esegue i tool;
  - il sandbox resta attivo (`sandbox_level: "high"`), lo stesso delle chat;
  - non serve il "full access" (`bypass_permissions`, `permission_mode: "full"`), che per le API key è comunque bloccato salvo `UNSLOTH_STUDIO_ALLOW_API_FULL_ACCESS=1`.
- **Autenticazione**: API key create con `POST /api/auth/api-keys` e inviate come `Authorization: Bearer <chiave>`.
- **Modello**: si carica una volta con `POST /api/inference/load` e si controlla con `GET /api/inference/status`.
- **Un avviso per sessione**: ogni richiesta contiene solo system prompt e "verifica il NNN", quindi è una conversazione nuova. La regola "un solo avviso per chat" del prompt resta come protezione per l'uso manuale.

## Flusso

1. **Arriva la lista** degli avvisi (export Mongo: JSON o JSONL).
2. **Divisione in file**: uno script Python (solo libreria standard, da scrivere) crea un file per avviso, `avvisi_da_verificare/NNN_<idAvviso>.json`; l'avviso si indica con il numero `NNN`. *Nel servizio: non serve, l'app manda gli avvisi in `POST /api/verifiche` e il servizio salva un file per avviso in `dati/avvisi/`.*
3. **Lanciatore** (PowerShell o bash, da scrivere). *Nel servizio: è la coda a 1 thread; il tool riceve dal servizio il percorso del file, non il numero.*
   1. carica il modello, una volta;
   2. per ogni file, **in sequenza** (un modello su CPU non regge richieste in parallelo), fa una richiesta a `/v1/chat/completions` con:
      - system: il contenuto di `src/main/python/prompt-di-sistema.md`;
      - user: `verifica il NNN`;
      - `enable_tools`, `enabled_tools`, `session_id` del progetto;
   3. salva la risposta testuale in un log; serve solo per controllo.
4. **Risultati**: lo script scrive gli esiti in `esiti/<giorno>/`, con una cartella per avviso (`esito.json`) e un `riepilogo.md` del giorno. Gli esiti non dipendono dal testo del modello.

## Tempi (stima)

Partendo dai circa 2 minuti per avviso misurati in chat: 100–200 avvisi fanno circa 3–7 ore in sequenza. Vanno bene per un job che parte di notte e finisce entro le 9.

Misurato con il servizio (2026-11-23, PC di sviluppo con i limiti della VM: 4 CPU, 8 GB, Ministral 3 3B): 7 avvisi in 17 s col modello, 9 s con lo script. Il modello aggiunge circa 1 s per avviso, perché genera solo la chiamata al tool; il resto è lo scaricamento delle pagine. Sulla VM vera i tempi vanno rimisurati.

## Variante: senza modello

Il modello non decide niente (fa una chiamata `python` e copia il blocco), quindi il job giornaliero può eseguire lo script da solo: `python -m verifica_gara avvisi_da_verificare`, pochi secondi per avviso, con gli stessi esiti. Il tempo totale scende da ore a minuti. Va concordato con ANAC, se si aspettano che il modello giri su ogni avviso.

## Da verificare con il prototipo

- [ ] Una chiamata reale a `/v1/chat/completions` con `enable_tools` e `session_id` del progetto: il modello chiama `verifica_gara` e la verifica finisce in `esiti/` della cartella del progetto.
- [ ] La versione di Unsloth nel Docker ha gli stessi campi dell'API.
- [ ] Via API viene aggiunto anche l'`AGENTS.md` del progetto, come in chat?
- [ ] Dentro il sandbox, chiamato via API, lo script riesce a scaricare le pagine (rete).
- [ ] Come creare l'API key e trovare l'id del progetto in un container senza interfaccia.
- [ ] Tempi reali per avviso via API, con e senza ripiego.

## Pezzi da scrivere

Non più necessari: `dividi_avvisi.py` e `lancia_verifiche.ps1` sono sostituiti dal servizio.
