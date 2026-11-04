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
- script: `verifica_gara.py` in questa cartella, che è la fonte unica del codice e si modifica direttamente;
- nel modello: `import verifica_gara`, con la chat **dentro il progetto** Unsloth che ha questa cartella.

Il prompt ha tre passi: 1 verifica, 2 ripiego web, 3 risposta.

### Checklist dopo ogni modifica
1. Se cambia `verifica_gara.py`: aumenta `VERSIONE`.
2. Aggiorna allo stesso valore ogni `versione="..."` in `prompt-di-sistema.md`.
3. Ricorda all'utente di reincollare `prompt-di-sistema.md` in Unsloth: con una versione diversa il modulo non dà esito e stampa un errore di versione.

## Vincoli di Unsloth (verificati nel suo codice)

Python di Unsloth: `C:/Users/Zzino/.unsloth/studio/unsloth_studio/Scripts/python.exe`. Sorgenti in `.../Lib/site-packages/studio/backend/core/inference/tools.py`.
- Nei tool `USERPROFILE`/`APPDATA` puntano alla cartella di lavoro: mai percorsi assoluti nel prompt.
- `subprocess`, terminale ed `echo` vengono bloccati dal controllo di sicurezza (`_check_code_safety`): il modello deve fare tutto con una chiamata `python` che importa il modulo.
- Il tool `python` (`_python_exec`) scrive il codice in un file `studio_exec_*.py` dentro la cartella di lavoro e lo lancia con `python -u`. Per questo un `.py` nella cartella di lavoro si importa senza percorsi.
- La cartella di lavoro è quella del progetto solo se la chat è in un progetto Unsloth; altrimenti è una sandbox per chat.
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
1. Copia `verifica_gara.py` nella cartella di prova.
2. Scrivi lì un `studio_exec_x.py` con il codice del Passo 1 del prompt.
3. Lancialo con `"<python di Unsloth>" -u studio_exec_x.py`.

Controllo di sicurezza sul codice che il modello scriverà (deve restituire `None`):
```python
from studio.backend.core.inference.tools import _check_code_safety  # con il Python di Unsloth
print(_check_code_safety(codice))
```
