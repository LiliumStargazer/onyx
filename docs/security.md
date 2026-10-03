# Sicurezza di Wiki Copilot

## Perimetro

Il progetto usa backend, frontend web, model server e strumenti di build, test e CI.
L'audit include anche le dipendenze Enterprise installate nelle immagini, senza abilitare funzionalità a pagamento.

`tools/wiki_copilot_security.py` definisce il filtro degli avvisi:

- Python: pacchetti esportati in `backend/requirements/{default,dev,ee,model_server}.txt`.
- Frontend: manifesti sotto `web/`, inclusi gli strumenti di build e test.
- GitHub Actions: `audit.yml`, `pr-quality-checks.yml` e `publish-wikijs-images.yml`.
- Strumenti Go: il modulo `tools/ods`, controllato dalla CI e usato per costruire il tool di audit.

Il filtro esclude desktop, widget, mobile, load test e workflow upstream disabilitati.
Non esclude un pacchetto solo perché una sua funzionalità è facoltativa.
Aggiorna il perimetro prima di aggiungere servizi, manifesti o workflow attivi.

## Controlli gratuiti

- Dependency graph e Dependabot rilevano le dipendenze e propongono aggiornamenti.
- L'audit OSV controlla i pacchetti Python, JavaScript, Go e le Actions.
- La CI usa Ruff, zizmor e ripsecrets per controllare codice, workflow e segreti.
- Questi strumenti non offrono tutta l'analisi dei percorsi dei dati di CodeQL.
- ripsecrets controlla i file del progetto; non sostituisce la scansione nativa della cronologia GitHub.

Ruff e ripsecrets rimangono nei Quality Checks. I segreti richiedono controlli anche nei file inattivi.
Una credenziale esposta può causare danni anche se il file che la contiene non entra nell'applicazione.

GitHub non offre CodeQL e secret scanning nativi sul normale repository privato personale.
Questo setup non usa GitHub Code Security, Secret Protection, upload SARIF o l'allowlist AWS upstream.
Le scansioni CI consumano la quota di minuti del piano GitHub.
Le protezioni native dei branch privati dipendono dal piano dell'account.

## Audit e pubblicazione

L'audit delle dipendenze esegue una scansione giornaliera.
La CI salva un riepilogo e report JSON per 14 giorni.
Le segnalazioni critiche nel perimetro bloccano la pubblicazione.
Errori dello scanner e report invalidi non diventano risultati positivi.
La CI compila `ods-audit` dal repository, con le dipendenze bloccate.
Lo scanner seleziona i tre workflow attivi prima di eliminare i duplicati.
Errori OSV parziali e riferimenti Action non verificati impediscono la pubblicazione.

La pubblicazione controlla anche l'immagine appena costruita, prima del push su GHCR.
L'audit settimanale controlla le immagini dei servizi Compose senza profili facoltativi.
Legge la configurazione Compose; non avvia, modifica o arresta servizi.

Imposta la variabile GitHub `DEPLOYED_IMAGE_TAG` sul tag effettivamente usato in Portainer.
Aggiornala dopo ogni deployment. Il valore non contiene il prefisso `v`.

## Filtro degli avvisi nativi

Il dependency graph rileva anche manifesti che il deployment non usa.
`DEPENDABOT_ALERTS_TOKEN` permette alla CI di archiviare questi avvisi con motivo `not_used`.
Il token deve essere fine-grained e limitato a questo repository, con `Dependabot alerts: read and write`.
La CI riapre solo gli avvisi archiviati dal proprio filtro quando tornano nel perimetro.
Non modifica le eccezioni manuali dei manutentori.

La sincronizzazione usa solo `main`, fuori dalle pull request, e richiede il token dedicato.
Le notifiche native possono precedere la sincronizzazione. Il riepilogo CI è già limitato al perimetro.
Il filtro non cancella advisory e non corregge vulnerabilità.

## Passaggio al repository privato

1. Conserva Git, issue, commenti e impostazioni prima di separare il fork.
2. Chiedi a GitHub una separazione che conservi i metadati, oppure concorda una migrazione alternativa.
3. Non usare `Leave fork network` senza accettare la perdita dei metadati indicata da GitHub.
4. Prepara le credenziali Portainer prima di cambiare la visibilità.
5. Verifica l'accesso autenticato al repository e al registry prima di rendere privato il codice.
6. Conserva il nome dello stack, il branch, i file Compose, i volumi e le variabili del deployment.

Portainer 2.39.5 usa autenticazione HTTPS per lo stack Git.
Crea un token fine-grained separato, con accesso al solo repository e `Contents: read-only`.
Non riusare il token della CI o una credenziale amministrativa.

Le immagini GHCR pubbliche contengono il codice distribuito.
Per limitare l'accesso al codice, rendi private anche le due immagini Wiki Copilot.
Portainer richiede un accesso GHCR separato con un token classic `read:packages`.
GitHub Packages non supporta i token fine-grained per questo accesso.

Salva le credenziali tramite `Edit stack settings`, senza selezionare `Redeploy`.
Mantieni `refs/heads/portainer-stack`, `docker-compose.yml` e `docker-compose.portainer-wikijs.yml`.
Non cambiare `IMAGE_TAG`, dominio, password o `USER_AUTH_SECRET` durante questa operazione.
Non cancellare lo stack e non rimuovere volumi.
