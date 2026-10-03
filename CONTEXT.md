# Wiki Agent Rag

Wiki Agent Rag è il prodotto che sostituirà Wiki Copilot. Usa la Wiki aziendale come fonte.

## Linguaggio

**Wiki Agent Rag**:
Il nome del prodotto che sostituirà Wiki Copilot, distinto dagli agenti disponibili al suo interno.
_Evitare_: AMWiki, Wiki.js, Wiki Copilot, nome dell'agente predefinito

**Assistant**:
L'agente predefinito di Wiki Agent Rag, distinto dal nome del prodotto e dagli agenti personalizzati.
_Evitare_: Wiki Agent Rag, wiki-am-agent

**Agente personalizzato**:
Agente configurato oltre ad Assistant. È distinto dal prodotto Wiki Agent Rag e dall'agente predefinito.
_Evitare_: Assistant, Wiki Agent Rag, Projects

**Wiki Copilot**:
L'assistente attuale che usa i contenuti della Wiki aziendale. È distinto da Wiki Agent Rag.
_Evitare_: nuovo assistente, Wiki.js

**Fonti**:
Documenti citati a sostegno di una risposta di Assistant, distinti dai documenti recuperati ma non citati.
_Evitare_: tutti i risultati della ricerca, allegati della chat

**PWA di Wiki Agent Rag**:
Versione installabile dal browser del sito Wiki Agent Rag. È distinta dall'app mobile nativa di Onyx.
_Evitare_: app mobile nativa, app da uno store

**Projects**:
Spazi personali di Onyx che raggruppano chat, file e istruzioni. Sono distinti dai progetti software e dagli agenti.
_Evitare_: repository, agente, cartella della Wiki

**Percorso pagina (`page_path`)**:
Percorso localizzato che identifica una pagina nel corpus. Uno spostamento o un cambio di nome crea un nuovo percorso.
_Evitare_: ID Wiki.js, titolo della pagina

**Ruolo**:
Profilo di accesso assegnato a un utente in base alla sua unità organizzativa (OU) Google Workspace. Determina quali contenuti può vedere.
_Evitare_: valore di visibility, permesso Wiki.js

**Valore di visibility**:
Etichetta di accesso associata ai contenuti della Wiki. Il ruolo dell'utente determina quali valori può consultare. I valori riservati non hanno un ordine unico di restrizione.
_Evitare_: ruolo, unità organizzativa

**Amministratore**:
Utente che gestisce Wiki Agent Rag. I suoi permessi di gestione sono distinti dal ruolo che determina i contenuti visibili.
_Evitare_: ruolo interni, primo utente generico

**Parità di accesso**:
Requisito per cui Wiki Agent Rag mantiene gli stessi utenti e la regola OU → ruolo → contenuti Wiki.js visibili di Wiki Copilot. La regola non modifica l'accesso alle altre fonti Onyx.
_Evitare_: stessa schermata di login, ACL native di Wiki.js
