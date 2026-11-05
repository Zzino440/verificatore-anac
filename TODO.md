# TODO - verifica automatica

Fonte: call "SAC2 - ANAC - test AI" del 2026-11-05 ([pagina Notion](https://app.notion.com/p/40f28f36105d8195a420c4d7c9783c68)) e messaggio di Matteo con i campi per tipologia.

## Subito
- [ ] **Oggi pomeriggio (2026-11-05)**: aggiornare Paride sull'esito del test del modello extractor.
- [ ] Scaricare il modello extractor proposto da Giuseppe (circa 876 MB, solo HTML, solo CPU), provarlo su Docker senza GPU e misurarne i tempi. Verificare se è lo stesso modello visto il giorno prima (circa 1,3 GB).

## Da chiedere
- [ ] **ANAC**: 3–4 esempi di verifiche manuali (cosa controllano, cosa ignorano). Servono per decidere quali campi accendere in `verifica_gara/campi.json`.
- [ ] **ANAC**: quale link va controllato tra `documenti_di_gara_link`, `avviso_pubblicato_committente_link` e i link ad accesso limitato. Oggi si apre solo `documenti_di_gara_link` (prima quello del lotto, poi quello della sezione B).
- [ ] **Matteo**: le liste di MODIFICHE_CONTRATTUALI e INDAGINI_DI_MERCATO_SOTTO_SOGLIA sono identiche. `valore_modifica` e `motivazione_modifica` non hanno senso per un'indagine di mercato: probabile errore di copia.
- [ ] **Matteo**: le schede con i campi obbligatori per template.
- [ ] **Giuseppe**: il link alla cartella dei documenti Mongo (Paride non la trova) e quello al modello extractor.
- [ ] Dalla cartella Mongo prendere **un avviso reale per ogni tipologia** e metterlo in `avvisi test/`. Finché mancano, le tipologie diverse da BANDI sono provvisorie: non conosciamo `tipo_oggetto`, la forma di aggiudicatari e durate, né la grafia esatta di `tipologia`.

## Sviluppo
- [ ] Tipologie senza CIG (ELENCHI_OPERATORI_ECONOMICI, AVVISI_DI_PRE-INFORMAZIONE_INFORMATIVI, SISTEMI_DI_QUALIFICAZIONE): decidere con cosa riconoscere la pagina (oggetto + stazione appaltante?). Oggi lo script le segnala come non ancora gestite.
- [ ] Accendere altri campi in `campi.json` (cpv, NUTS, ISTAT, sì/no, durata…) dopo gli esempi di ANAC.
- [ ] Job giornaliero (per esempio alle 9) sugli avvisi pubblicati il giorno prima, solo non scaduti: 100–200 al giorno, nessuna verifica retroattiva.
- [ ] Dashboard da `esito.json` / `riepilogo.md` in Python, senza AI (bassa priorità).
- [ ] PDF e immagini: fuori ambito, da riconsiderare solo se ANAC lo chiede.

## Presentazione per ANAC (in pending finché il flusso non è consolidato)
Decisione della call: si comunica con ANAC tramite documentazione/PowerPoint, non con una demo, perché il referente (Prato) preferisce leggere.
- [ ] La presentazione la prepara Paride, con gli screenshot degli output, e la manda ad ANAC insieme a template e istruzioni, chiedendo se vanno aggiornati.
- [ ] Da confermare con Paride la parte mia: gli screenshot degli output (blocco di risposta, `riepilogo.md`, `esito.json`) e un breve testo su flusso, esiti (`verificato` / `dubbio` / `non_verificabile`) e cause.
- [ ] Contenuti utili:
  - architettura: lo script fa il lavoro deterministico, il modello piccolo interviene solo nel ripiego web;
  - i tre casi della demo: verificato, dubbio sull'importo nel caso dei 4 lotti, link a un'altra gara;
  - tempi: circa 10 secondi con lo script; i circa 15 minuti su Docker venivano dal modello che ricopiava il testo, ed è quello che il batch elimina;
  - volumi della fase sperimentale.
- [ ] Valutare la presentazione integrata di Claude (tipo Slides degli Artifact, si esporta in .pptx) invece di farla a mano. Il vincolo "niente AI esterna" riguarda il prodotto, non la comunicazione interna.
