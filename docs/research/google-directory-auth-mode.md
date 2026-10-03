# Google Directory in Wiki Copilot legacy e Wiki Copilot

Verifica statica del codice. Non è stata eseguita una richiesta a Google Directory.

- Wiki Copilot legacy richiede in produzione `GOOGLE_DIRECTORY_AUTH_MODE`, `GOOGLE_SA_JSON` e `OU_ROLE_MAP`. `GOOGLE_DELEGATED_ADMIN` è facoltativo nella modalità diretta. Fonte: `../wiki-copilot-legacy/docker-compose.prod.yml:50-56`.
- La modalità `service_account` usa le credenziali del service account senza impersonificazione. La modalità `delegated_user` aggiunge `GOOGLE_DELEGATED_ADMIN` come subject. Entrambe leggono il JSON da `GOOGLE_SA_JSON` e richiedono lo scope `admin.directory.user.readonly`. Fonti: `../wiki-copilot-legacy/assistant-api/src/assistant_api/auth.py:147-175`; `../wiki-copilot-legacy/docs/security.md:19-26`.
- Il codice crea le credenziali con `Credentials.from_service_account_info(json.loads(config.GOOGLE_SA_JSON), ...)`. La chiave è quindi contenuta in una variabile d'ambiente, non in un file separato. Fonte: `../wiki-copilot-legacy/assistant-api/src/assistant_api/auth.py:153-170`.
- La configurazione di produzione rifiuta modalità assente o sconosciuta e JSON assente o non valido. La delega richiede un utente Workspace diverso dal service account. Fonte: `../wiki-copilot-legacy/assistant-api/src/assistant_api/config.py:311-338`.
- Wiki Copilot non usa attualmente `GOOGLE_DIRECTORY_AUTH_MODE` o `GOOGLE_SA_JSON` per il login. Legge invece un file tramite `GOOGLE_DIRECTORY_SERVICE_ACCOUNT_FILE`; `GOOGLE_DIRECTORY_ADMIN_EMAIL` abilita la delega. Fonte: `backend/onyx/auth/google_workspace.py:82-98`.

Per configurare Directory senza Portainer, un futuro provider Google dovrà conservare il JSON come segreto cifrato, oltre alla mappa OU e alla modalità. La modalità da sola non dà accesso a Directory. L'accesso diretto richiede verifica operativa nel Workspace; la documentazione di Wiki Copilot legacy prevede una prova e, se Google lo nega, il passaggio esplicito alla delega. Fonte: `../wiki-copilot-legacy/docs/operations.md:290-314`.
