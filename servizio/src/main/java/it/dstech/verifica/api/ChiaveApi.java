package it.dstech.verifica.api;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/** /api/** richiede l'header X-API-Key uguale ad API_KEY; senza API_KEY rifiuta tutto. */
@Component
public class ChiaveApi extends OncePerRequestFilter {

    private final String chiave;

    public ChiaveApi(@Value("${verifica.api-key}") String chiave) {
        this.chiave = chiave;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest req) {
        return !req.getRequestURI().startsWith("/api/");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain)
            throws ServletException, IOException {
        if (chiave.isBlank() || !chiave.equals(req.getHeader("X-API-Key"))) {
            res.sendError(HttpServletResponse.SC_UNAUTHORIZED, "X-API-Key mancante o errata");
            return;
        }
        chain.doFilter(req, res);
    }
}
