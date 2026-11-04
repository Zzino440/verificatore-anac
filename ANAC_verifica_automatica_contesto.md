# ANAC – Verifica automatica dei link degli avvisi: contesto di progetto

Documento di contesto per le chat AI su questo progetto. Aggiornato al 2026-11-03.

## In breve

Per il cliente ANAC (piattaforma PVL, sviluppi DIG_12) DSTech sta progettando un sistema che controlla che il link `documenti_di_gara_link` di ogni avviso porti davvero alla pagina del bando. Il controllo verifica che la pagina riporti CIG, importo, scadenza e oggetto. L'esito viene solo registrato: nessun link o avviso viene modificato.

Il nome ufficiale è **"verifica automatica"**. Su richiesta del cliente non va mai chiamato "AIGIS" né presentato come "progetto AI", per evitare che venga percepito come un modo scorretto di gestire il processo.

**Da non confondere** con il plugin che gestisce i ticket PCP per lo stesso cliente (DB NPA, report ticket): è un progetto separato.

## Persone

| Persona | Ruolo |
| --- | --- |
| Francesco Appratto | Referente ANAC; decide perimetro e vincoli. Nelle trascrizioni compare anche come "Prato". |
| Paride Criscio | DSTech, coordinamento e rapporto con il cliente. |
| Matteo Parisi | DSTech, autore dell'analisi iniziale; ha provato Mistral 7B in locale dentro un'app Java. |
| Lorenzo Belli | DSTech, riferimento tecnico AI; autore dei test con modello locale e della skill. |
| Andrea Battista | DSTech, frontend/GIS (documento GIS, tema separato). |

## Problema

Ogni avviso inviato ad ANAC contiene un link alla documentazione di gara sul portale della stazione appaltante. PVL pubblica solo un estratto del bando e rimanda a quel link per i dettagli. Spesso però il link:

- non è raggiungibile;
- porta alla home generica della stazione appaltante o a un elenco di bandi, invece che alla pagina del bando;
- porta a una pagina intermedia, da cui serve un clic in più (spesso dentro liste paginate);
- porta a una pagina corretta, ma con contenuti poco accessibili: immagini, allegati non cliccabili, caricamento via JavaScript.

## Decisioni prese (call con il cliente del 2026-10-13 e allineamenti interni)

1. **Fase 1 solo bandi**, circa 100 link al giorno (AD3 e categorie numerose escluse). In una stima precedente si parlava di 600 avvisi al giorno, con possibile crescita.
2. **Si parte dall'HTML della pagina.** Gli allegati (PDF, Excel, CAD/BIM, formati open) sono rinviati a fasi successive.
3. **Niente AI esterna in Fase 1.** Non è una questione di privacy: servirebbe una policy aziendale ANAC, con un iter stimato di circa 6 mesi. Resta un'ipotesi per una fase 2.
4. **AI interna ammessa solo se sostenibile**, senza macchine più potenti di quelle esistenti. Altrimenti si ripiega su una soluzione deterministica. Il cliente però ci tiene ad avere una componente AI, anche come base per usi futuri.
5. **Infrastruttura:** container su Azure, in futuro su PSN, **senza GPU**. CPU e RAM non sono ancora note.
6. **Architettura modulare:** step indipendenti, modificabili singolarmente, con un formato di output modificabile dall'esterno.
7. **Approccio misto:** gli script fanno estrazione e confronto, l'AI interviene il meno possibile. È una richiesta esplicita del cliente, per contenere contesto e consumi.
8. Il servizio è **esplorativo**: dà un indicatore probabilistico e non sostituisce il controllo umano.

## Test con modelli locali (2026-10-14)

- **Qwen 3.5 9B**, contesto 64k, su GPU consumer: esito corretto su due avvisi di prova (un link rotto riconosciuto come "non verificabile", una discrepanza di orario segnalata). Tempo: 2-3 minuti per link. Il modello tende a ragionare troppo.
- Gli stessi casi con modelli cloud danno lo stesso esito in meno di 30 secondi.
- Su sola CPU la stima è di 10-15 minuti per avviso. Con 8k di contesto e la pagina intera il modello non riesce ad analizzare quasi nulla.
- Conclusione: il modello **non deve leggere la pagina intera**. Gli script devono fornirgli solo un pacchetto di prove già filtrato.
- **Il test in Docker su sola CPU non è ancora stato fatto.**

## Soluzione realizzata: skill `verifica-automatica` (v0.3)

È una cartella skill con script Python e un `README.md` completo all'interno. Usa un flusso in tre step indipendenti, che comunicano tramite file JSON.

1. **Step 1 – Input** (`step1_input.py` + `avviso.py`)
   - Normalizza l'avviso ANAC (`templates → sections → items`) in una lista di lotti.
   - Scarica ogni link una sola volta e rileva errori e redirect.
   - Pulisce il testo e conserva a parte header e footer ("cornice").
   - Se il CIG manca, segue fino a 5 link scelti per somiglianza con CIG e oggetto.
   - Riconosce le pagine caricate via JavaScript.
2. **Step 2 – Analisi** (`step2_analisi.py`)
   - Per ogni lotto cerca CIG, importo (anche in formato italiano), scadenza (formati e fusi orari multipli), oggetto (copertura delle parole) e stazione appaltante (CF o denominazione).
   - Le regole decidono i casi chiari. Solo i lotti ambigui vengono marcati con `richiede_giudizio` e passati al modello, con un pacchetto di circa 3 KB.
3. **Step 3 – Output** (`step3_output.py`)
   - Produce il record finale secondo `config/output_template.json`, modificabile senza toccare il codice.

**Formato dell'esito:** per ogni lotto uno tra `verificato`, `dubbio`, `non_verificabile`, con motivo, riscontri per campo e `fonte_esito` (`regole` o `modello`). L'esito dell'avviso è quello del lotto peggiore.

**Scelte tecniche:**

- Nessun harness pesante tipo Claude Code: il suo system prompt saturerebbe il contesto di un modello piccolo.
- Integrazione consigliata: il verificatore Java orchestra gli script e chiama il modello solo per i lotti ambigui.
- Il CIG è la prova principale, perché è univoco. Senza CIG l'esito non può mai essere `verificato`.
- Le scadenze negli avvisi arrivano a volte in UTC (`Z`) e a volte con offset. Lo script accetta sia l'orario così come è scritto sia quello convertito in ora italiana, per evitare falsi allarmi.

**Test:** 7 casi offline, tutti con l'esito atteso. Includono due avvisi reali:

- **MAECI, CIG BD4F2406B3:** il link Traspare `/announcements/90142` reindirizza all'elenco generale dei bandi → `non_verificabile`.
- **Comune di Casalnuovo di Napoli, CIG BD594390B5:** portale Maggioli, testato con una pagina di dettaglio simulata → `verificato`. Con orario sbagliato il caso diventa ambiguo.

## Punti aperti

- **Risorse del container** Azure/PSN (CPU, RAM): da chiedere ad Appratto.
- **Test del modello** in Docker su sola CPU, misurando i tempi del solo giudizio sui casi ambigui.
- **Dove salvare l'esito:** aggiornare `stato` dell'avviso (oggi `NON_VERIFICATO`) oppure una collection separata.
- **robots.txt:** alcuni portali (es. Maggioli) vietano l'accesso automatico; da decidere con ANAC come comportarsi.
- **Playwright:** il rendering delle pagine JavaScript è implementato ma disattivato e non collaudato. Il cliente ha chiesto riferimenti su manutenzione e community prima di adottarlo.
- **Prove sui siti reali** dalla rete di progetto: la VPN ANAC può rallentare o bloccare la navigazione.
- **Documento di analisi per Appratto** da aggiornare con nome, perimetro Fase 1, architettura proposta e stima dei consumi.

## Formato dell'avviso in ingresso (campi usati)

```
idAvviso, codiceScheda, tipologia, dataScadenza.$date
templates[0].template.metadata.descrizione
sections[*].fields.soggetti_sa[0].{codice_fiscale, denominazione_amministrazione}
sections[*].fields.documenti_di_gara_link
sections[*].items[*] (tipo_oggetto = lotto): cig, descrizione,
    valore_complessivo_stimato, termine_ricezione, documenti_di_gara_link
```

## Glossario

| Termine | Significato |
| --- | --- |
| CIG | Codice identificativo di gara, univoco per lotto. |
| PVL / PWL | Piattaforma ANAC che pubblica l'estratto degli avvisi (Angular 16); nelle trascrizioni compare spesso come "PWL". |
| PCP | Piattaforma dei contratti pubblici, da cui arrivano gli avvisi (`dataPCP`). |
| PSN | Polo Strategico Nazionale, cloud della PA. |
| AD3 | Categoria di avvisi molto numerosa, esclusa dalla Fase 1. |
| DIG_12 / DIG_13 | Pacchetti di lavoro ANAC. Questa analisi rientra in DIG_12; DIG_13 riguarda audit e cruscotto BO. |
| Verificatore | Applicazione Java in cui integrare la skill e salvare l'esito su DB. |

## Fonti in Notion

- Meeting 2026-10-13 11:00 "ANAC – Allineamento interno doc AI GIS"
- Meeting 2026-10-13 16:00 "SAC2 – ANAC – DIG_PVL_13 – review doc GIS & AI" (call con Appratto)
- Meeting 2026-10-14 10:00 "Revisione Doc AI" (test con modelli locali, architettura a skill)
- Appunti Ottobre 2026 → "Anac" (messaggio al cliente con i risultati del test) e "IA in locale anac"
