# Private Google Workspace login setup

Do not publish this stack or sync the real Wiki for this test.

1. Apply the database migration. Keep the stack on a private network. Set a stable `USER_AUTH_SECRET` with at least 32 characters before storing Directory credentials. Changing it later makes the encrypted credentials unreadable.
2. Configure a Google OAuth client with `openid email profile` scopes. In **Organization → SSO Providers**, create a Google provider with your Workspace email domain. Register the displayed return URI with Google.
3. Edit the provider. Set the OU-to-role JSON map to verified Directory paths, including the admin's OU. Example: `{"/Interni AM":"interni","/Agenti":"agente"}`. Allowed roles: `interni`, `tecnico`, `agente`, `concessionario`. No default role exists.
4. Enter the complete service account JSON used by Wiki Copilot legacy's `GOOGLE_SA_JSON`. Directory authentication uses `service_account` directly with user-read-only scope, without delegation. The JSON is encrypted before storage and masked in the admin response. Do not paste it in logs, issues, or chat.
5. While signed in as the existing password admin, select **Link my Google account** on the Google provider. Complete Google login with the *same* verified Workspace email. This links the stable Google subject to the existing Onyx account; it never links by email alone. Confirm that a subsequent Google login opens the same admin account.
6. Only after a successful private test, disable password login and public registration in **Organization → Security & Hardening**. Do not make the stack public before later access-control tickets pass.

Legacy environment-variable Google routes still use `OU_ROLE_MAP` and `GOOGLE_DIRECTORY_SERVICE_ACCOUNT_FILE`. Do not configure that route for this stack; remove legacy OAuth client settings when switching to the provider. Missing or invalid provider settings deny login. Directory errors deny login without deleting the user. The content role is independent of Onyx admin permissions. Ticket #18 adds checks for existing sessions and the absolute session limit. Ticket #19 connects the role to Wiki document access.
