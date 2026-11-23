package it.dstech.verifica.coda;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import it.dstech.verifica.esecuzione.Script;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Un avviso alla volta: il file va in DATI_DIR/avvisi/, gli stati restano in memoria. */
@Service
public class CodaVerifiche {

    private final ExecutorService esecutore = Executors.newSingleThreadExecutor();
    private final Map<String, Verifica> verifiche = new ConcurrentHashMap<>();
    private final ObjectMapper json;
    private final Script script;
    private final Path avvisi;

    public CodaVerifiche(ObjectMapper json, Script script, @Value("${verifica.dati-dir}") Path datiDir) throws IOException {
        this.json = json;
        this.script = script;
        this.avvisi = Files.createDirectories(datiDir.resolve("avvisi"));
    }

    public String accoda(JsonNode avviso) throws IOException {
        Verifica v = new Verifica(UUID.randomUUID().toString());
        json.writeValue(avvisi.resolve(v.id + ".json").toFile(), avviso);
        verifiche.put(v.id, v);
        esecutore.submit(() -> esegui(v));
        return v.id;
    }

    private void esegui(Verifica v) {
        v.stato = "in_corso";
        try {
            v.esito = script.esegui("avvisi/" + v.id + ".json");
            v.stato = "fatto";
        } catch (Exception e) {
            v.errore = e.getMessage();
            v.stato = "errore";
        }
    }

    public Verifica trova(String id) {
        return verifiche.get(id);
    }

    public List<Verifica> delGiorno(LocalDate giorno) {
        return verifiche.values().stream()
                .filter(v -> v.creata.toLocalDate().equals(giorno))
                .sorted(Comparator.comparing(v -> v.creata))
                .toList();
    }
}
