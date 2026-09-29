# Private Google Workspace login setup

Do not publish this stack or sync the real Wiki for this test.

1. Apply the database migration. Keep the stack on a private network.
2. Configure a Google OAuth client with `openid email profile` scopes. Set its return URI from **Organization → SSO Providers**. Add the verified Workspace email domain there. Alternatively, set the legacy `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, and `VALID_EMAIL_DOMAINS` settings.
3. Set `OU_ROLE_MAP` to the verified OU paths from the active Workspace configuration. Example: `{"/Interni AM":"interni","/Agenti":"agente"}`. The admin's OU must also be mapped. Allowed roles are `interni`, `tecnico`, `agente`, and `concessionario`. No default role exists.
4. Set `GOOGLE_DIRECTORY_SERVICE_ACCOUNT_FILE` to the path of a private Google service account JSON key with Directory user read access. For delegated access, set `GOOGLE_DIRECTORY_ADMIN_EMAIL` to the authorized admin account. Keep the file outside the repository. Mount it with `api.volumes` and `api.volumeMounts` in Helm, or a private Docker volume.
5. Create the first admin through Google while the stack is private. Confirm access to the Admin Panel. Google login does not claim an existing password account with the same email. If that account exists, use a new, authorized Google admin identity; do not relink by email.
6. After a successful private test, disable password login and public registration in **Organization → Security & Hardening**. Do not make the stack public before the later access-control tickets pass.

`OU_ROLE_MAP` enables the Workspace login check. Invalid maps deny Google login. Directory errors deny login without deleting the user. The content role is stored separately from Onyx admin permissions. Ticket #18 adds checks for existing sessions and the absolute session limit. Ticket #19 connects the content role to Wiki document access.
