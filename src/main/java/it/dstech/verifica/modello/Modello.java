package it.dstech.verifica.modello;

import com.fasterxml.jackson.databind.JsonNode;
import it.dstech.verifica.esecuzione.Script;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;

/** MODALITA=modello: il modello vede solo il tool verifica_avviso, legato all'avviso del job. */
@Component
public class Modello {

    private final ChatClient chat;
    private final Script script;
    private final String prompt;

    public Modello(ChatModel model, Script script, @Value("classpath:prompt-servizio.md") Resource prompt) throws Exception {
        this.chat = ChatClient.create(model);
        this.script = script;
        this.prompt = prompt.getContentAsString(StandardCharsets.UTF_8);
    }

    /** L'esito viene dall'esecuzione del tool, mai dal testo del modello. */
    public JsonNode esegui(String avviso) throws Exception {
        Strumento s = new Strumento(avviso);
        chat.prompt().system(prompt).user("Verifica l'avviso.").tools(s).call().content();
        if (!s.chiamato) throw new IllegalStateException("il modello non ha chiamato il tool verifica_avviso");
        if (s.errore != null) throw s.errore;
        return s.esito;
    }

    /** Un'istanza per job: senza argomenti, esegue lo script una sola volta sul file dell'avviso. */
    class Strumento {
        private final String avviso;
        volatile boolean chiamato;
        volatile JsonNode esito;
        volatile Exception errore;

        Strumento(String avviso) {
            this.avviso = avviso;
        }

        @Tool(name = "verifica_avviso", returnDirect = true,
                description = "Verifica l'avviso assegnato e restituisce l'esito. Non ha argomenti.")
        String verificaAvviso() {
            if (!chiamato) {
                chiamato = true;
                try {
                    esito = script.esegui(avviso);
                } catch (Exception e) {
                    errore = e;
                }
            }
            return errore != null ? "errore: " + errore.getMessage() : "esito: " + esito.path("esito").asText();
        }
    }
}
