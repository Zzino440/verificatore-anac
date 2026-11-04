# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Progetto

"Verifica automatica" per ANAC (DSTech): controlla che il `documenti_di_gara_link` di un avviso porti a una pagina che riporta CIG, importo, scadenza e oggetto di ogni lotto. Contesto completo (cliente, vincoli, decisioni, persone, glossario) in `ANAC_verifica_automatica_contesto.md`.
- Nome ufficiale: "verifica automatica". Mai "AIGIS" né "progetto AI" (richiesta del cliente).
- Vincoli: niente AI esterna, container senza GPU, modello locale piccolo che interviene il meno possibile. La logica deterministica sta nello script; il modello lo chiama e riporta l'output.
- Il documento di contesto descrive anche la skill `verifica-automatica` (v0.3, tre step). È un lavoro precedente e separato: il flusso attivo è quello qui sotto.

## Due flussi paralleli, stesso script

Il modello gira in **Unsloth Studio** (tool `python` e `web_search`). Lo stesso processo è disponibile in due forme che **vanno tenute sempre allineate**: ogni modifica alla logica o alle istruzioni si applica a entrambe, senza che l'utente debba ricordarlo.

| | Flusso skill | Flusso system prompt |
|---|---|---|
| Istruzioni | `C:\Users\Zzino\.claude\skills\controllo-link-gara\SKILL.md` | `prompt-di-sistema.md` (in questa cartella) |
| Script | modulo `controllo_link_gara` nel `site-packages` di Unsloth, installato da `installa.py` | `verifica_gara.py` in questa cartella |
| Import nel modello | `import controllo_link_gara` | `import verifica_gara` |
| Uso in Unsloth | skill abilitata | prompt incollato nel System prompt, chat **dentro il progetto** con questa cartella, skill disattivata |

**Fonte unica del codice:** `C:\Users\Zzino\.claude\skills\controllo-link-gara\scripts\verifica.py`. Non modificare `verifica_gara.py` direttamente: è una copia. I due file di istruzioni hanno gli stessi passi (1 verifica, 2 ripiego web, 3 risposta). Cambiano solo il nome del modulo, il messaggio per modulo mancante o versione sbagliata e l'introduzione: il prompt non ha frontmatter, si apre con "Sei il verificatore…" e spiega che "SKILL.md" nell'output indica il prompt.

### Checklist dopo ogni modifica
1. Se cambia `scripts/verifica.py`: aumenta `VERSIONE`.
2. Aggiorna allo stesso valore ogni `versione="..."` in `SKILL.md` **e** in `prompt-di-sistema.md`. Se cambia il testo delle istruzioni, cambialo in entrambi.
3. Reinstalla e ricopia:
   ```bash
   cd "C:/Users/Zzino/.claude/skills/controllo-link-gara" && python installa.py
   cp "C:/Users/Zzino/.claude/skills/controllo-link-gara/scripts/verifica.py" "Z:/Zzino/Projects/AI/verificatore-anac/verifica_gara.py"
   ```
4. Ricorda all'utente di reincollare `prompt-di-sistema.md` in Unsloth: con una versione diversa il modulo non dà esito e stampa un errore di versione.

## Vincoli di Unsloth (verificati nel suo codice)

Python di Unsloth: `C:/Users/Zzino/.unsloth/studio/unsloth_studio/Scripts/python.exe`. Sorgenti in `.../Lib/site-packages/studio/backend/core/inference/tools.py`.
- Il modello **non conosce il percorso della skill** (nei tool `USERPROFILE`/`APPDATA` puntano alla cartella di lavoro). Mai percorsi assoluti in SKILL.md o nel prompt.
- `subprocess`, terminale ed `echo` vengono bloccati dal controllo di sicurezza (`_check_code_safety`): il modello deve fare tutto con una chiamata `python` che importa il modulo.
- Il tool `python` (`_python_exec`) scrive il codice in un file `studio_exec_*.py` dentro la cartella di lavoro e lo lancia con `python -u`. Per questo un `.py` nella cartella di lavoro si importa senza percorsi.
- La cartella di lavoro è quella del progetto solo se la chat è in un progetto Unsloth; altrimenti è una sandbox per chat.
- Il modello è piccolo: istruzioni brevi e imperative, una sola chiamata `python` per avviso. Copia spesso male il JSON (parentesi): lo script ripiega su `leggi_per_campi`, che legge i valori campo per campo.

## Come funziona lo script

`esegui("avviso.json", versione=..., [lotto=CIG, cig, importo, scadenza, oggetto] | [nonraggiungibile=CIG])`
1. Il modello scrive il JSON incollato in `avviso.json` nella cartella di lavoro (file di passaggio, sovrascritto ogni volta) e chiama `esegui`.
2. Lo script scarica la pagina con urllib (solo libreria standard) e confronta i campi: importo in formati IT/EN, scadenza con orario così com'è o convertito in ora italiana, oggetto per copertura delle parole.
3. Come prova della verifica stampa l'URL scaricato, il codice HTTP, il titolo della pagina e, per ogni campo, l'estratto della pagina in cui l'ha trovato. Il modello deve riportare l'output **così com'è**.
4. Se la pagina non è utilizzabile (redirect, pagina quasi vuota/JS, CIG assente) stampa `FALLBACK_WEB <url> lotto <CIG>`. Il modello apre la pagina con `web_search(url=...)` e richiama `esegui` con i valori copiati (`lotto=...`) oppure con `nonraggiungibile=...`.
5. Esiti per lotto: `verificato`, `dubbio`, `non_verificabile`. L'esito dell'avviso è quello del lotto peggiore. Senza CIG nella pagina non è mai `verificato`.

Output su disco:
```
esiti/AAAA-MM-GG/riepilogo.md                       tabella delle verifiche del giorno
esiti/AAAA-MM-GG/NNN_HH-MM-SS_<idAvviso>/avviso.json + esito.json
```
Una nuova verifica crea una cartella con `NNN` progressivo del giorno. Le chiamate di ripiego (`lotto`/`nonraggiungibile`) aggiornano l'ultima cartella dello stesso `idAvviso`.

## Prove

Avvisi di esempio in `avvisi test/`. MAECI Madrid (`BC515775D3`) → `verificato`.

Per simulare una chiamata esattamente come la fa Unsloth, eseguila in una cartella di prova nello scratchpad, così non sporchi `esiti/` del progetto:
1. Copia `verifica_gara.py` nella cartella di prova.
2. Scrivi lì un `studio_exec_x.py` con il codice del Passo 1 del prompt.
3. Lancialo con `"<python di Unsloth>" -u studio_exec_x.py`.

Controllo di sicurezza sul codice che il modello scriverà (deve restituire `None`):
```python
from studio.backend.core.inference.tools import _check_code_safety  # con il Python di Unsloth
print(_check_code_safety(codice))
```
