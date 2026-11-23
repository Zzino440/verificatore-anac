package it.dstech.verifica.esecuzione;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

/** Lancia {@code python -m verifica_gara <avviso> --json} nella cartella DATI_DIR e restituisce esito.json. */
@Component
public class Script {

    private final ObjectMapper json;
    private final String python;
    private final Path scriptDir;
    private final Path datiDir;
    private final Duration timeout;

    public Script(ObjectMapper json,
                  @Value("${verifica.python}") String python,
                  @Value("${verifica.script-dir}") Path scriptDir,
                  @Value("${verifica.dati-dir}") Path datiDir,
                  @Value("${verifica.script-timeout}") Duration timeout) {
        this.json = json;
        this.python = python;
        this.scriptDir = scriptDir.toAbsolutePath();
        this.datiDir = datiDir.toAbsolutePath();
        this.timeout = timeout;
    }

    /** {@code avviso} e' relativo a DATI_DIR. Un errore dello script diventa un'eccezione con la causa. */
    public JsonNode esegui(String avviso) throws Exception {
        File out = datiDir.resolve(avviso + ".out").toFile();
        File err = datiDir.resolve(avviso + ".err").toFile();
        ProcessBuilder pb = new ProcessBuilder(python, "-m", "verifica_gara", avviso, "--json")
                .directory(datiDir.toFile()).redirectOutput(out).redirectError(err);
        pb.environment().put("PYTHONPATH", scriptDir.toString());
        Process p = pb.start();
        if (!p.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS)) {
            p.destroyForcibly();
            throw new IllegalStateException("lo script non ha finito entro " + timeout.toSeconds() + " s");
        }
        String stdout = Files.readString(out.toPath(), StandardCharsets.UTF_8);
        if (p.exitValue() != 0) {
            String causa;
            try {
                causa = json.readTree(stdout).path("errore").asText();
            } catch (Exception e) {
                causa = "";
            }
            if (causa.isEmpty()) {
                causa = "exit " + p.exitValue() + ": " + Files.readString(err.toPath(), StandardCharsets.UTF_8).strip();
            }
            throw new IllegalStateException(causa);
        }
        String run = json.readTree(stdout).path("run").asText();
        return json.readTree(datiDir.resolve(run).resolve("esito.json").toFile());
    }
}
