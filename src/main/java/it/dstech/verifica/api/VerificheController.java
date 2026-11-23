package it.dstech.verifica.api;

import com.fasterxml.jackson.databind.JsonNode;
import it.dstech.verifica.coda.CodaVerifiche;
import it.dstech.verifica.coda.Verifica;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/verifiche")
public class VerificheController {

    private final CodaVerifiche coda;

    public VerificheController(CodaVerifiche coda) {
        this.coda = coda;
    }

    /** Un avviso JSON o una lista di avvisi: 202 con gli id, nello stesso ordine. */
    @PostMapping
    public ResponseEntity<Map<String, List<String>>> accoda(@RequestBody JsonNode body) throws IOException {
        List<JsonNode> avvisi = new ArrayList<>();
        if (body.isArray()) body.forEach(avvisi::add); else avvisi.add(body);
        if (avvisi.isEmpty() || avvisi.stream().anyMatch(a -> !a.isObject())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "serve un avviso JSON o una lista di avvisi");
        }
        List<String> ids = new ArrayList<>();
        for (JsonNode a : avvisi) ids.add(coda.accoda(a));
        return ResponseEntity.accepted().body(Map.of("ids", ids));
    }

    @GetMapping("/{id}")
    public Verifica stato(@PathVariable String id) {
        Verifica v = coda.trova(id);
        if (v == null) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "verifica " + id + " non trovata");
        return v;
    }

    @GetMapping
    public List<Verifica> delGiorno(@RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate giorno) {
        return coda.delGiorno(giorno);
    }
}
