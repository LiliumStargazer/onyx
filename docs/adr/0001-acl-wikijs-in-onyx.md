# Applicare la visibility Wiki.js tramite le ACL di Onyx

Wiki Agent Rag mantiene la regola OU → ruolo → visibility di Wiki Copilot per i documenti Wiki.js. Il backend applica le ACL Onyx: associa ogni pagina alla sua visibility e il ruolo corrente ai valori ammessi. I metadati non limitano l'accesso, i gruppi del connettore non distinguono le pagine e le ACL Wiki.js non sostituiscono la regola. Decisione: [#9](https://github.com/LiliumStargazer/wiki-agent-rag/issues/9).
