# Piano: verifica automatica collegata a pvl-verifier e mostrata nel cruscotto BO

> Stato al 2026-11-24. Da condividere con Matteo Parisi (BE/cruscotto), Giuseppe Zangara (pvl-verifier) e Andrea Battista (FE). Il microservizio è descritto in `PIANO_MICROSERVIZIO.md` e nel `README.md` della radice.

## Contesto

Il microservizio "verifica automatica" (`verificatore-anac`, Spring Boot 3.5.4 + script Python) è pronto. Funziona così:
- `POST /api/verifiche` riceve un avviso o una lista e risponde `202` con gli id;
- `GET /api/verifiche/{id}` e `GET /api/verifiche?giorno=` danno lo stato e, a verifica finita, il contenuto di `esito.json`;
- l'autenticazione è con `X-API-Key`; gli stati stanno in memoria.

L'obiettivo è che gli esiti, per avviso e per lotto (`verificato` / `dubbio` / `non_verificabile`, con causa, motivo e campi atteso/trovato), compaiano nel cruscotto del backoffice PVL. Il piano deve essere pulito e scalabile.

### Cosa c'è oggi (letto sui branch remoti dopo `git fetch`)

**pvl-verifier** (`origin/final_dig_13` = `feature/verificatore-avvisi-ai`)
- È un worker schedulato, senza DB e senza API (solo `HealthController`).
- `VerificaUrlJob` gira ogni 2 ore. Legge le regole da `get-regole-analisi`, prende gli avvisi del giorno da `/api/v0/avvisi`, estrae `documenti_di_gara_link` e controlla solo la raggiungibilità.
- Per ogni esito manda un evento `tipo=Esito` OK/NOK tramite spool su file, con POST `save-log/{eventId}` su pvl-backend.
- Il ramo `compatibilitaUrl=true` è già previsto, ma oggi scrive solo un log (`VerificaUrlJob.java:173`) e `NON_ESEGUITO` nella chiusura (`:260`). **È il punto d'aggancio naturale.**

**pvl-backend** (`origin/sviluppo_dig013`)
- `save-log` salva in `logsArchive` un log grezzo: nessuna proiezione per avviso, nessun indice.
- `get-logs` accetta solo OK/NOK.
- Ogni NOK con `tipo=Esito` entra nel conteggio delle notifiche strutturali.
- Le regole di analisi (`raggiungibilitaUrl`, `compatibilitaUrl`, `tipologie`) stanno in `cataloghiRegole/_id=analisi`.

**pvl-bo-backend** (`origin/sviluppo_DIG_13_BO`, Boot 2.7.4)
- È il BFF del backoffice, con Feign `PVLClient` verso pvl-backend e JWT.

**pvl-bo-frontend** (`origin/sviluppo_DIG_013`, Angular 12, NgModule)
- Ha già una sezione **Verificatore**: `verificatore/visione-audit` (`gest-verificatore`) e `amm/gestione-verificatore` (regole di "corrispondenza" e "alert").
- `VerificatoreService` chiama `api/pvl-bo/verificatore/esiti`, `/csv` e `/{id}/report`, con modello `EsitoVerifica {id, tipo, descrizione, esito, dataEsito}`.
- I campi e i filtri (`stato` OK/NOK, `tipo`, date, pagina) ricalcano `VerifierEvent` e `get-logs`. Matteo ha aggiunto la paginazione a `get-logs` il 23/11.
- **Quindi la "Visione audit" è il visore degli eventi di audit in `logsArchive`, non uno spazio libero.**
- La verifica automatica avrà **pagina, modello e namespace propri** nella sezione Verificatore. La Visione audit resta com'è e mostrerà in più gli eventi del run (inizio, fine, conteggi).

## Decisione

| Domanda | Risposta | Perché |
|---|---|---|
| Aggiungere il microservizio all'ecosistema? | **Sì, come servizio interno separato** (container a sé, nella stessa rete dei backend, senza ingresso pubblico) | Lo decide anche la call del 23/11 ("microservizio separato, collegato al verificatore, per non sporcarlo"). Ha un runtime diverso (Python, ed eventualmente llama.cpp), un ciclo di rilascio e versioni propri, e si scala o sostituisce da solo |
| Il FE lo chiama direttamente? | **No** | La chiave API finirebbe nel browser. Il FE conosce solo Keycloak e `pvlBoApi`. Gli stati del servizio stanno in memoria e si perdono al riavvio. Il servizio sta in una rete interna. Si salterebbero BFF e audit |
| Lo si porta dentro pvl-verifier? | **No** (niente porting delle regole in Java) | Le regole hanno una sola fonte, lo script, già provata sui 7 casi. pvl-verifier resterebbe con Python e modello dentro un'immagine JDK |
| Come si collega? | **pvl-verifier orchestra, pvl-backend conserva, pvl-bo-backend espone, il FE mostra** | Ognuno fa il suo mestiere. Gli esiti diventano dati interrogabili, non log |

```
           cron giornaliero / avvio manuale per giorno
                         │
                   pvl-verifier ──GET /api/v0/avvisi (JSON grezzo)──► pvl-backend
                         │
     POST /api/verifiche (lista), GET /api/verifiche/{id} (X-API-Key, rete interna)
                         ▼
               verifica-automatica (MS) [+ llm, se MODALITA=modello]
                         │ esito.json per avviso
                         ▼
   pvl-verifier ──spool su file──► POST /api/v0/pvl-bo/verifiche-automatiche/{id}
                                     │ (pvl-backend, collection verificheAutomatiche)
                                     ▼
   pvl-bo-frontend ──► pvl-bo-backend /api/pvl-bo/verifiche-automatiche* ──Feign──► pvl-backend
```

Gli **esiti per avviso** vanno in una collection dedicata, non in `logsArchive`, per quattro motivi:
- servono un esito a tre valori, i lotti e i filtri per esito, tipologia, CIG e giorno, con KPI;
- `get-logs` accetta solo OK/NOK;
- i NOK gonfierebbero le notifiche strutturali;
- il log non ha né id né indice per avviso.

Su `logsArchive` restano solo gli **eventi di audit del run** (inizio e fine, con i conteggi), come già fanno le altre fasi.

L'esito è una **dimensione separata** (scelta confermata) e lo `stato` dell'avviso (KO/WARNING/…) non si tocca.

---

## Fase 0 — Contratto dell'avviso ✅ (fatta)

> **Stato (24/11, chat a parte, risultato ricontrollato qui).** Sono stati scaricati 216 avvisi del 17–23/11 da `testpubblicitalegale.anticorruzione.it/api/v0/avvisi`, di cui 64 BANDI. Lo script è stato lanciato su 8 BANDI presi così come arrivano.
> - **Lettura corretta, nessuna modifica allo script, `VERSIONE` invariata:**
>   - `tipologia: BANDI` corrisponde a `campi.json`;
>   - lotti e CIG vengono trovati, anche quando i lotti sono 2;
>   - le date ISO (`2026-11-19T10:00:00+01:00`) si leggono bene.
> - **Confronto con le pagine non ancora provato:** in collaudo tutti gli avvisi risultano `non_verificabile`. È corretto, perché i CIG sono finti (`I033…`) e i portali di test rimandano alla home oppure non esistono nel DNS.
> - **Resta aperto un punto:** provare almeno un avviso di pre-esercizio o di produzione per vedere un `verificato` e un `dubbio` (rientra nella Fase 6).
> - **Utile per la Fase 2:** il filtro `dataPubblicazioneStart/End` dell'API accetta solo `dd/MM/yyyy`, e pvl-verifier lo formatta già così.
>
> I passi qui sotto restano come riferimento per ripetere il controllo.

Lo script è stato provato su export Mongo (`dataScadenza.$date`). `/api/v0/avvisi` invece serializza `AvvisoWithTemplate` con date ISO (`2025-01-01T00:00:00.000+00:00`) e `tipologia` al primo livello.

1. Prendere 3–5 avvisi BANDI reali da `/api/v0/avvisi` in sviluppo e salvarli così come arrivano.
2. Lanciare `python -m verifica_gara <file> --json` su ciascuno.
3. Controllare tre cose:
   - che `tipologia` corrisponda alle chiavi di `campi.json`;
   - che le date dei lotti (`termine_ricezione`) siano lette bene;
   - che i lotti si trovino in `templates[0].template.sections[*].items[*]`.
4. Se serve correggere `avviso.py` o `campi.json`, è una modifica allo script: va alzato `VERSIONE` (patch) come da `CLAUDE.md`.
5. Aggiungere un avviso reale anonimizzato in `avvisi_da_verificare/`, con il suo esito atteso nel README.

**Fatto quando:** gli avvisi reali danno un esito sensato senza errori di lettura.

## Fase 1 — Microservizio (`verificatore-anac`)

Le API vanno già bene e non cambiano.
- pvl-verifier usa `POST /api/verifiche` con una lista, poi interroga `GET /api/verifiche/{id}` **solo per gli id ancora in coda o in corso**.
- Non si usa `?giorno=` per due motivi: restituisce ogni volta tutti gli esiti completi accumulati nel giorno; e quel giorno è la data di arrivo sul servizio, non la data di pubblicazione, quindi un run a cavallo della mezzanotte si spezzerebbe.
- Evolutiva facoltativa: `GET /api/verifiche/stati?ids=…`, solo stati, in una chiamata. È una funzionalità nuova e compatibile, quindi alza la minor.
- La Fase 0 non ha richiesto correzioni allo script.
- Il riavvio del servizio fa perdere gli stati in memoria. È accettabile: pvl-verifier rimanda gli id che non trova più (vedi Fase 2). Va scritto nel README del servizio.
- `esito.json` ha già `versione`: pvl-backend la salva, così si sa con quali regole è stato prodotto un esito.

## Fase 2 — pvl-verifier (orchestrazione)

Il branch di partenza è da decidere con Giuseppe (vedi Punti aperti). Il disegno vale per entrambi.

**Package nuovo `verificaautomatica`**
- **`VerificaAutomaticaClient`**:
  - è modellato su `backend/PvlBackofficeClient.java`: `RestTemplateBuilder`, timeout da proprietà, header `X-API-Key`, costruttore package-private per `MockRestServiceServer`;
  - metodi `health()`, `invia(List<JsonNode>) → ids`, `verifica(id)`.
- **Avvisi grezzi**:
  - nuovo metodo in `verificaurl/PvlPublicClient` che restituisce `List<JsonNode>` (o `ObjectNode`) per giorno e template;
  - così `tipologia`, `dataScadenza` e tutti i campi passano invariati. `AvvisoResponseDto` ne tiene solo 4.
  - Il job URL resta com'è.
- **`VerificaAutomaticaJob`**:
  - è un job **separato** da `VerificaUrlJob`, con il suo scheduler in `config/SchedulerConfig` e il suo cron (default giornaliero, es. `0 0 6 * * *`, sugli avvisi pubblicati il giorno prima);
  - è separato perché dura minuti (polling), non deve bloccare la raggiungibilità ogni 2 ore e va eseguito **una volta per giorno di pubblicazione**, non 12.
  - Al posto del log a `VerificaUrlJob.java:173` resta un rimando al job dedicato. `compatibilitaUrl` nella chiusura dice `JOB_DEDICATO`.
- **Flusso di `esegui(LocalDate giorno)`**:
  1. regole (`getRegoleAnalisi`): esce se `compatibilitaUrl` non è true; prende le tipologie abilitate (via `TipologieTemplateResolver`);
  2. avvisi grezzi del giorno, solo attivi e non oscurati;
  3. `health()` del servizio: se è giù, evento audit NOK e uscita;
  4. invio a blocchi (es. 50 avvisi);
  5. polling degli id ancora aperti, con `verifica(id)`, ogni N secondi, finché tutti sono `fatto`/`errore` o scade il timeout del run (es. 30 minuti). Un id che risponde 404 (servizio riavviato) viene rimandato **una volta**;
  6. per ogni avviso costruisce il payload `EsitoVerificaAutomatica` (vedi Fase 3) e lo mette nello **spool**.
- **Giornata specifica** (richiesta di ANAC):
  - `POST /internal/verifica-automatica/esecuzioni?giorno=AAAA-MM-GG`, protetto da un header con chiave (filtro nuovo e minimale);
  - un cron disattivabile (`-`) permette la modalità "solo manuale" per contenere i costi.
- **Idempotenza**: l'id dell'esito è `<idAvviso>_<giorno>`, quindi rieseguire un giorno sovrascrive (upsert) e non duplica.
- **Spool e invio**:
  - riusa il meccanismo di `VerifierEventSpool` / `VerifierEventSender`, con una cartella dedicata e il target `verifiche-automatiche/{id}`;
  - **un 400 non si scarta in silenzio**: il file va in `scartati/` con log ERROR.
- **Audit del run**:
  - si riusano gli eventi di fase esistenti, con un `flow` nuovo (`VERIFICA_AUTOMATICA`) e `dettagli` con i conteggi (verificati, dubbi, non verificabili, errori) e la durata;
  - **nessun evento `Esito` per avviso**, così le notifiche strutturali non si gonfiano;
  - aggiungere il valore anche ai due `switch` esaustivi, `RegoleStrutturaliService.java:65` e `CadfAuditEventPublisher.java:101`.
- **Configurazione** (variabili d'ambiente): `VERIFICA_AUTOMATICA_URL`, `VERIFICA_AUTOMATICA_API_KEY`, `JOB_VERIFICA_AUTOMATICA_ENABLED`, `CRON_JOB_VERIFICA_AUTOMATICA`, `VERIFICA_AUTOMATICA_TIMEOUT_RUN`, `VERIFICA_AUTOMATICA_POLLING`, `VERIFICA_AUTOMATICA_BLOCCO`, `VERIFICA_AUTOMATICA_SPOOL_DIR`, `INTERNAL_API_KEY`.
- **Test**:
  - client con `MockRestServiceServer`;
  - job con client finti: tutto fatto, timeout, id persi e rimandati, servizio giù, regola spenta;
  - spool: 400 messo in `scartati/`, errore transitorio riprovato.

## Fase 3 — pvl-backend (persistenza e lettura)

**Collection `verificheAutomatiche`** (`@Document`), un documento per avviso e giorno:
```
_id: "<idAvviso>_<giorno>"
idAvviso, codiceScheda, tipologia, giorno (LocalDate di pubblicazione), dataEsito (Date), runId
esito: VERIFICATO | DUBBIO | NON_VERIFICABILE | ERRORE   (dell'avviso = lotto peggiore)
causa, motivo                                           (del lotto peggiore)
url, versioneRegole                                     (esito.json.versione)
lotti: [{ cig, esito, causa, motivo, campiDiversi: [nome...] }]
esitoCompleto: { ...esito.json }                        (campi atteso/trovato/estratto, pagina)
```
- **Indici**: `idAvviso`; `{giorno, esito}`; `{tipologia, giorno}`; `lotti.cig`; `dataEsito`.
- **Endpoint** sotto `/api/v0/pvl-bo/`, già coperto da `ApiKeyInterceptor` con Bearer, che si usa così com'è:
  - `POST verifiche-automatiche/{id}`: upsert. Risponde 400 se l'id del path è diverso da quello del body o se `esito` è fuori dall'enum.
  - `GET verifiche-automatiche`: paginato. Filtri `esito`, `tipologia`, `idAvviso`, `cig`, `dataEsitoDa`/`dataEsitoA`, `giorno`; ordinamento.
  - `GET verifiche-automatiche/{id}`: dettaglio con `esitoCompleto`.
  - `GET verifiche-automatiche/avviso/{idAvviso}`: l'ultimo esito dell'avviso, per il tab del dettaglio bando.
  - `GET verifiche-automatiche/kpi?da&a`: conteggi per esito, e per tipologia e causa (aggregation).
  - `GET verifiche-automatiche/csv`.
- **Pattern**: controller e service come quelli esistenti in `PVLBOController` / `PVLBOServiceImpl`, con i test sullo stesso stile.

## Fase 4 — pvl-bo-backend (BFF)

- **Feign** in `client/PVLClient.java`: un metodo per ogni endpoint della Fase 3, con gli header `Authorization` e `Bearer_user` come gli altri.
- **Controller** `api/pvl-bo/verifiche-automatiche`, un namespace proprio. `verificatore/esiti` resta alla Visione audit e a `get-logs`:
  - `GET` paginato, filtri `esito`, `tipologia`, `idAvviso`, `cig`, `dataEsitoDa`/`dataEsitoA`;
  - `GET /csv`;
  - `GET /{id}`: dettaglio JSON;
  - `GET /{id}/report`: download dell'`esito.json` come file;
  - `GET /kpi`;
  - `GET /avviso/{idAvviso}`.
- **DTO** propri (`VerificaAutomaticaDto`, `VerificaAutomaticaDettaglioDto`), passati così come arrivano da pvl-backend.
- **Sicurezza**: JWT come il resto e ruolo `PVLBO`.

## Fase 5 — pvl-bo-frontend (cruscotto)

Branch `sviluppo_DIG_013`. I pattern esistenti:
- componenti in `_core/components/anac-*`, dichiarati in `AppModule`;
- rotte con `data.roles: ["PVLBO"]`;
- ui-kit `lib-anac-table` / `-tab` / `-chip` / `-card`;
- testi in i18n (3 file);
- spec con TestBed e `jasmine.createSpyObj`.

`EsitoVerifica`, `VerificatoreService` e la Visione audit non si toccano.

1. **Modelli** (file nuovo `model/verificaAutomatica.ts`):
   - `VerificaAutomatica {id, idAvviso, codiceScheda, tipologia, giorno, dataEsito, esito, causa, motivo, url, numeroLotti}`;
   - `VerificaAutomaticaDettaglio` con `lotti[{cig, esito, causa, motivo, campi: {nome: {atteso, trovato, ok, estratto}}}]` e `pagina`;
   - `FiltroVerificheAutomatiche`;
   - costanti degli esiti separate da `STATI`.
   - Service nuovo `verifica-automatica.service.ts`, sullo stesso schema di `verificatore.service.ts`.
2. **Pagina "Verifica automatica"** (componente nuovo `anac-gest-verifica-automatica`, rotta `verificatore/verifica-automatica`, voce nella sidebar della sezione Verificatore):
   - filtri: esito, tipologia, idAvviso, CIG, date;
   - colonne: data, idAvviso, tipologia, esito (chip colorato: verde, giallo, rosso, grigio), causa, motivo;
   - CSV e azione "dettaglio".
3. **Dettaglio verifica**:
   - componente nuovo `anac-dettaglio-verifica`, rotta `verificatore/verifica-automatica/dettaglio/:id`;
   - una tabella per lotto (CIG, esito, causa, motivo) e, espandendo, i campi atteso/trovato/ok con l'estratto;
   - link alla pagina verificata, link "vai all'avviso" (`home/bandi/dettaglio/:id`), download del report.
4. **Tab "Verifica automatica"** in `dettaglio-bando` (`initTabs()`): l'ultimo esito dell'avviso (`/avviso/{idAvviso}`), riusando il componente del punto 3 in versione incorporata.
5. **KPI**:
   - card in testa alla pagina "Verifica automatica" (e, se piace, in `home-ko`) con i conteggi per esito della settimana;
   - il link porta alla lista già filtrata.
6. **i18n** (it/en/de): esiti, cause (`tutto_trovato`, `campi_diversi`, `cig_assente`, `altra_gara`, `pagina_non_raggiungibile`, `link_assente`), etichette.
7. **Test** per service e componenti nuovi, con i pattern esistenti. Lo sviluppo del FE può partire subito con mock dal contratto OpenAPI delle Fasi 3–4.

## Fase 6 — Deploy

- **Immagine del servizio** nel registry Azure del progetto (`$AZURE_REGISTRY_HOST/anac/verifica-automatica`), costruita in CI come pvl-backend (Kaniko).
- **Esecuzione PaaS** (decisione del 23/11): Azure Container Apps o App Service per container, con ingresso **solo interno** nella stessa VNet o subnet di pvl-verifier.
  - Con `MODALITA=modello`, `llm` va come secondo container interno, con il GGUF su Azure Files.
  - `DATI_DIR` può restare effimero, perché gli esiti stanno in Mongo.
- **Segreti** (`API_KEY`) in Key Vault o nei secret dell'app, mai nei file.
- **pvl-verifier**: le variabili della Fase 2. All'inizio `JOB_VERIFICA_AUTOMATICA_ENABLED=true` con il cron spento e avvio manuale per giorno, come chiesto da ANAC.
- **In locale**: `docker compose` del servizio, più pvl-verifier col profilo `dev` puntato al pvl-backend di sviluppo.

## Ordine di lavoro

| # | Cosa | Chi (proposta) | Dipende da |
|---|---|---|---|
| 0 | ✅ Contratto avviso reale ↔ script | Lorenzo | — |
| A | OpenAPI di `verifiche-automatiche` su pvl-backend e BO (contratto condiviso) | Lorenzo + Matteo | 0 |
| 1 | Servizio: nota sul riavvio nel README; nessuna correzione allo script | Lorenzo | 0 |
| 2 | pvl-verifier: client, job, spool, trigger | Lorenzo / Giuseppe | A |
| 3 | pvl-backend: collection e API | Matteo | A |
| 4 | pvl-bo-backend: BFF | Matteo | A (mock) → 3 |
| 5 | FE cruscotto | Andrea | A (mock) → 4 |
| 6 | Deploy in pre-esercizio, prova su un giorno reale (primi `verificato`/`dubbio` su avvisi veri) | Lorenzo | 1–5 |

2, 3, 4 e 5 possono andare in parallelo una volta fissato il contratto A.

**Evolutive** (non nell'MVP):
- colonna e filtro "verifica automatica" in `gestione-ko`, denormalizzando `{esito, dataEsito, id}` sull'avviso e aggiornando l'indice Atlas;
- le "regole di corrispondenza" del BO che alimentano `campi.json`, passate al servizio nella richiesta;
- callback al posto del polling;
- alert sulla soglia di `dubbio`.

## Verifica end-to-end

1. **Script**: i 7 avvisi di esempio danno gli esiti del loro README; gli avvisi reali della Fase 0 si leggono senza errori.
2. **pvl-verifier**:
   - unit test verdi (`./mvnw test`);
   - in locale, `POST /internal/verifica-automatica/esecuzioni?giorno=…` → log del run con i conteggi;
   - nello spool, un file per avviso che si svuota.
3. **pvl-backend**:
   - in `verificheAutomatiche`, un documento per avviso con esito e lotti;
   - rieseguendo lo stesso giorno il numero di documenti non cambia (upsert);
   - `GET …/kpi` è coerente con i documenti.
4. **Casi di errore**:
   - servizio spento: evento audit NOK, nessun esito perso;
   - servizio riavviato durante il run: gli id vengono rimandati e gli esiti arrivano;
   - payload non valido: il file finisce in `scartati/`.
5. **BO**: tutte le chiamate di `verifiche-automatiche*` provate (collection Postman aggiornata) con un JWT di sviluppo.
6. **FE**:
   - nella pagina "Verifica automatica" i 7 avvisi appaiono con chip ed esiti attesi;
   - in Visione audit compaiono gli eventi di inizio e fine run;
   - il dettaglio mostra i lotti e i campi;
   - il tab "Verifica automatica" del bando 04 mostra il dubbio sull'importo;
   - CSV e report si scaricano.

## Punti aperti (da decidere col team)

- **Branch base di pvl-verifier**: `final_dig_13` oppure `sviluppo_dig_13`, che è un rifacimento parallelo con 138 file diversi, un altro sistema di eventi e cron `23:30`. Da decidere con Giuseppe prima della Fase 2.
- **Chi costruisce il BFF di `verificatore/esiti` → `get-logs`** per la Visione audit: è un lavoro separato da questo, da allineare con Matteo e Andrea. Con l'occasione va chiarito se le "regole di corrispondenza" del BO vadano un giorno ad alimentare `campi.json`.
- **Chi avvia la "giornata specifica"**: l'endpoint interno di pvl-verifier lo usano solo gli sviluppatori. Per ANAC (costi, demo) servirebbe dal BO, in due modi possibili:
  - un campo "giorno da verificare" in `cataloghiRegole/analisi`, letto dal job;
  - un pulsante in `amm-verificatore`.
- **Giorno verificato**: avvisi pubblicati ieri o oggi? Escludere quelli scaduti?
- **Conservazione di `esitoCompleto`**: gli estratti pesano qualche KB per avviso. Va deciso se togliere `estratto` dopo N giorni.
- **Formato di `/{id}/report`**: JSON oppure HTML o PDF leggibile.

## Problemi trovati fuori ambito (da segnalare, non toccare ora)

- **`Dockerfile` di pvl-verifier**: usa JDK 17 mentre il pom chiede Java 21. Inoltre il launcher `org.springframework.boot.loader.JarLauncher` è sbagliato con Boot 3.2+.
- **`tipo="audit"` minuscolo** negli eventi di fase di pvl-verifier, mentre il BE cerca `"Audit"`: le fasi NOK non arrivano mai alle notifiche strutturali.
- **pvl-bo-backend** chiama `get-cronologia-pre-pubblicazione` in POST, mentre il BE lo espone in GET.
- **Default in chiaro** per credenziali in `application.properties` di pvl-verifier (i valori non si riportano qui).
