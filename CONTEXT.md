# Assistente Wiki aziendale

Questo fork di Onyx sostituirà Wiki Copilot. Il nome del nuovo assistente è ancora da decidere.

## Linguaggio

**Wiki Copilot**:
L'assistente attuale che usa i contenuti della Wiki aziendale. È distinto dal nuovo assistente basato su Onyx.
_Evitare_: nuovo assistente, Wiki.js

**Ruolo**:
Profilo di accesso assegnato a un utente in base alla sua unità organizzativa (OU) Google Workspace. Determina quali contenuti può vedere.
_Evitare_: valore di visibility, permesso Wiki.js

**Valore di visibility**:
Etichetta di accesso associata ai contenuti della Wiki. Il ruolo dell'utente determina quali valori può consultare.
_Evitare_: ruolo, unità organizzativa

**Parità di accesso**:
Requisito per cui il nuovo assistente mantiene gli stessi utenti e la regola OU → ruolo → contenuti visibili di Wiki Copilot.
_Evitare_: stessa schermata di login, ACL native di Wiki.js
