package it.dstech.verifica.coda;

import com.fasterxml.jackson.databind.JsonNode;

import java.time.LocalDateTime;

/** Una verifica: stato in_coda, in_corso, fatto o errore; esito e' il contenuto di esito.json. */
public class Verifica {
    public final String id;
    public final LocalDateTime creata = LocalDateTime.now();
    public volatile String stato = "in_coda";
    public volatile JsonNode esito;
    public volatile String errore;

    Verifica(String id) {
        this.id = id;
    }
}
