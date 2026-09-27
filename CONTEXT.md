# Wiki Agent Rag

Wiki Agent Rag è il prodotto che sostituirà Wiki Copilot. Usa la Wiki aziendale come fonte.

## Linguaggio

**Wiki Agent Rag**:
Il nome del prodotto che sostituirà Wiki Copilot, distinto dagli agenti disponibili al suo interno.
_Evitare_: AMWiki, Wiki.js, Wiki Copilot, nome dell'agente predefinito

**Assistant**:
L'agente predefinito di Wiki Agent Rag, distinto dal nome del prodotto e dagli agenti personalizzati.
_Evitare_: Wiki Agent Rag, wiki-am-agent

**Wiki Copilot**:
L'assistente attuale che usa i contenuti della Wiki aziendale. È distinto da Wiki Agent Rag.
_Evitare_: nuovo assistente, Wiki.js

**Ruolo**:
Profilo di accesso assegnato a un utente in base alla sua unità organizzativa (OU) Google Workspace. Determina quali contenuti può vedere.
_Evitare_: valore di visibility, permesso Wiki.js

**Valore di visibility**:
Etichetta di accesso associata ai contenuti della Wiki. Il ruolo dell'utente determina quali valori può consultare.
_Evitare_: ruolo, unità organizzativa

**Parità di accesso**:
Requisito per cui Wiki Agent Rag mantiene gli stessi utenti e la regola OU → ruolo → contenuti visibili di Wiki Copilot.
_Evitare_: stessa schermata di login, ACL native di Wiki.js
