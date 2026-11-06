# Avvisi da verificare

Un avviso ANAC in JSON per file. Per aggiungerne uno basta salvarlo qui come `NN_descrizione.json`.

- In chat si verifica **un avviso per chat**, indicato con il numero ("verifica il 3"). Il modello chiama `verifica_gara.esegui("3")`. Se il numero corrisponde a nessun file o a più di uno, il modulo dà errore e mostra l'elenco.
- Tutta la cartella, senza modello: `python -m verifica_gara avvisi_da_verificare`.

Esempi di partenza, da [Esempi bandi ANAC Appratto](https://app.notion.com/p/40d28f36105d80698023d79c9cb36c4c) (tutti MAECI su maeci.traspare.com, tipologia BANDI):

| file | cosa mette alla prova | esito atteso |
|---|---|---|
| `01_buenos_aires_link_home.json` | il link reindirizza alla pagina iniziale del portale, che elenca altre gare | `non_verificabile` (altra gara), il motivo cita il redirect |
| `02_madrid_base.json` | caso base, tutti i dati sulla pagina | `verificato` |
| `03_francoforte_scadenza_utc.json` | scadenza in UTC nel JSON, ora italiana nella pagina | `verificato` |
| `04_corsi_lingue_4_lotti_importo_errato.json` | 4 lotti nella stessa pagina, importo del lotto 4 sbagliato (59.000 invece di 95.000) | `dubbio` solo su `B64522444F` |
| `05_cairo_gara_annullata.json` | gara annullata, dati corretti | `verificato` (lo stato della gara non è controllato) |
| `06_madrid_manutenzione_importo_parziale.json` | importo soggetto a ribasso invece del totale | `verificato` (basta che il numero compaia) |
| `07_francoforte_link_altra_gara.json` | dati di Francoforte con il link della gara di Madrid | `non_verificabile` (altra gara) |
