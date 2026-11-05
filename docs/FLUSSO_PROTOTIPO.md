# Flusso del prototipo: verifica automatica su macchina o Docker

Obiettivo: verificare ogni giorno gli avvisi (100–200, solo non scaduti) senza aprire le chat di Unsloth a mano, con **un avviso per sessione del modello**.

Stato: fattibile secondo il codice di Unsloth Studio installato. **Non ancora provato con chiamate reali.**

## Cosa offre Unsloth Studio

Verificato nei sorgenti di `studio/backend` della versione installata, non nella documentazione online.

- **API compatibile con OpenAI**: `POST /v1/chat/completions` (`routes/inference.py`). Si mandano i messaggi system (il prompt) e user ("verifica il 03"), più alcuni campi propri di Unsloth:
  - `enable_tools: true` ed `enabled_tools: ["python", "web_search"]`: i tool girano **sul server**, con lo stesso ciclo della chat (chiamata `python`, eventuale `FALLBACK_WEB`, `web_search`, nuova chiamata `python`), tutto in una sola richiesta;
  - `session_id: "project-<id progetto>"`: le chiamate `python` girano nella **cartella del progetto**, dove stanno `../verifica_gara` e `avvisi_da_verificare/` (`_project_workdir_for` in `core/inference/tools.py`).
- **Permessi**:
  - senza `permission_mode` esplicito, una richiesta non in streaming non chiede conferme ed esegue i tool;
  - il sandbox resta attivo (`sandbox_level: "high"`), lo stesso delle chat;
  - non serve il "full access" (`bypass_permissions`, `permission_mode: "full"`), che per le API key è comunque bloccato salvo `UNSLOTH_STUDIO_ALLOW_API_FULL_ACCESS=1`.
- **Autenticazione**: API key create con `POST /api/auth/api-keys` e inviate come `Authorization: Bearer <chiave>`.
- **Modello**: si carica una volta con `POST /api/inference/load` e si controlla con `GET /api/inference/status`.
- **Un avviso per sessione**: ogni richiesta contiene solo system prompt e "verifica il NNN", quindi è una conversazione nuova. La regola "un solo avviso per chat" del prompt resta come protezione per l'uso manuale.

## Flusso

1. **Arriva la lista** degli avvisi (export Mongo: JSON o JSONL).
2. **Divisione in file**: uno script Python (solo libreria standard, da scrivere) crea un file per avviso, `avvisi_da_verificare/NNN_<idAvviso>.json`. Con l'`idAvviso` nel nome l'avviso si indica anche per id, e `_trova_avviso` lo trova già.
3. **Lanciatore** (PowerShell o bash, da scrivere):
   1. carica il modello, una volta;
   2. per ogni file, **in sequenza** (un modello su CPU non regge richieste in parallelo), fa una richiesta a `/v1/chat/completions` con:
      - system: il contenuto di `../prompt-di-sistema.md`;
      - user: `verifica il NNN`;
      - `enable_tools`, `enabled_tools`, `session_id` del progetto;
   3. salva la risposta testuale in un log; serve solo per controllo.
4. **Risultati**: lo script scrive gli esiti in `esiti/<giorno>/`, con una cartella per avviso (`avviso.json`, `esito.json`, `risposta.md`) e un `riepilogo.md` del giorno. Gli esiti non dipendono dal testo del modello.

## Tempi (stima)

Partendo dai circa 2 minuti per avviso misurati in chat: 100–200 avvisi fanno circa 3–7 ore in sequenza. Vanno bene per un job che parte di notte e finisce entro le 9. Il ripiego web costa di più, perché il modello deve leggere la pagina e copiarne i valori: il totale dipende da quanti avvisi finiscono lì.

## Variante: modello solo per il ripiego web

1. Il lanciatore esegue prima lo script da solo: `python -m verifica_gara avvisi_da_verificare`, pochi secondi per avviso.
2. Apre una sessione del modello **solo per gli avvisi con `FALLBACK_WEB`**.

Gli esiti restano gli stessi, perché li decide sempre lo script, e il tempo totale scende da ore a minuti. È più vicino al vincolo "modello che interviene il meno possibile", ma va concordato con ANAC, se si aspettano che il modello giri su ogni avviso.

## Da verificare con il prototipo

- [ ] Una chiamata reale a `/v1/chat/completions` con `enable_tools` e `session_id` del progetto: il modello chiama `verifica_gara` e la verifica finisce in `../esiti`.
- [ ] La versione di Unsloth nel Docker ha gli stessi campi dell'API.
- [ ] Via API viene aggiunto anche l'`../AGENTS.md` del progetto, come in chat?
- [ ] Dentro il sandbox, chiamato via API, lo script riesce a scaricare le pagine (rete).
- [ ] Il ripiego web (`web_search`) funziona via API, provato con l'esempio 01 di Buenos Aires.
- [ ] Come creare l'API key e trovare l'id del progetto in un container senza interfaccia.
- [ ] Tempi reali per avviso via API, con e senza ripiego.

## Pezzi da scrivere

- `dividi_avvisi.py`: dalla lista ai file `NNN_<idAvviso>.json`.
- `lancia_verifiche.ps1` (o `.sh`): caricamento del modello, ciclo sugli avvisi, log.
