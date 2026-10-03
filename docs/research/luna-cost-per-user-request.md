# Costo di una richiesta utente con GPT-6 Luna

Ricognizione del 3 ottobre 2026. Esempio: «fammi vedere i listini della Athena».
Questa nota riguarda la nuova pipeline Onyx in `wiki-copilot`, non quella del vecchio `wiki-copilot-legacy`.
La prima ricognizione conteneva solo stime. Il primo test utente è stato interrotto.
Il secondo test, «Listino Athena», ha prodotto una risposta completa con ragionamento Low.
I consumi dei due test sono separati sotto.

## Tariffe verificate

Fonti ufficiali: [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna),
[prezzi API](https://developers.openai.com/api/docs/pricing) e
[token di ragionamento](https://developers.openai.com/api/docs/guides/reasoning).

Prezzi Standard, in USD per milione di token:

| Tipo | Prezzo |
| --- | ---: |
| Ingresso senza cache | $0,10 |
| Lettura della cache | $0,01 |
| Scrittura della cache | $0,125 |
| Uscita | $0,50 |

I token di ragionamento sono fatturati come token di uscita. Non contare soltanto la risposta visibile.
Sopra 272.000 token in ingresso, una singola chiamata ha tariffe maggiorate per l'intera chiamata.
Il modello applica un aumento del 10% agli endpoint regionali disponibili.
Gli scenari sotto usano Standard, senza cache e senza endpoint regionali.
Ogni singola chiamata resta sotto la soglia del contesto lungo.

## Perché una domanda costa più di una chiamata

Il costo dipende da tutte le chiamate causate dal messaggio, non dalla sola frase dell'utente.
Il prompt include istruzioni, cronologia e contenuto dei documenti.

Il codice corrente esegue:

- chiamate del ciclo chat per scegliere gli strumenti e produrre la risposta:
  [`llm_loop.py`](../../backend/onyx/chat/llm_loop.py), `run_llm_loop`;
- riformulazione semantica e query per parole chiave; eventuali filtri di fonte e tempo:
  [`search_tool.py`](../../backend/onyx/tools/tool_implementations/search/search_tool.py),
  `_expand_queries_and_decide_scope`;
- selezione delle sezioni e, quando applicabile, classificazione del contesto per ciascuna sezione:
  [`document_filter.py`](../../backend/onyx/secondary_llm_flows/document_filter.py) e
  [`search_utils.py`](../../backend/onyx/tools/tool_implementations/search/search_utils.py);
- eventuali chiamate ulteriori, per esempio il titolo della nuova chat:
  [`chat_session_naming.py`](../../backend/onyx/secondary_llm_flows/chat_session_naming.py).

Il filtro di fonte non chiama il modello con meno di due fonti connesse.
La selezione ha un budget indicativo di 25.600 token con i valori predefiniti:
25 chunk × 512 token × moltiplicatore 2. Non è il costo massimo dell'intero messaggio.
Fonti: `MAX_CHUNKS_FED_TO_CHAT`, `DOC_EMBEDDING_CONTEXT_SIZE` e `SELECTION_TOKEN_BUDGET_MULTIPLIER`.

[`tool_constructor.py`](../../backend/onyx/tools/tool_constructor.py) passa il modello della chat alla ricerca interna.
Il primo controllo del database locale non aveva trovato provider o consumi.
Il test successivo ha usato lo stack remoto funzionante, con GPT-6 Luna come modello predefinito.

## Test utente interrotto

Domanda inviata: «fammi vedere i listini della athena».
L'utente ha usato la propria sessione autorizzata. Non abbiamo modificato ruoli o ACL.

- Baseline: 3 ottobre 2026, 09:08:49 UTC.
- Avvio del messaggio: 09:08:58 UTC.
- Prima ricerca: 8 documenti inviati allo stream, entro circa 09:09:06 UTC.
- Attesa lunga: chiamata al modello avviata circa 09:09:07, con usage restituita alle 09:20:12 UTC.
- Chiusura dello stream: `done=true`, evento `stop`, motivo `user_cancelled`.
- Lettura dei consumi dopo l'interruzione: 09:22:10 UTC.

Il database non contiene altri nuovi messaggi dello stesso utente nell'intervallo osservato.
Abbiamo sottratto la baseline dai contatori giornalieri per utente, modello, operazione e provider.
Tutte le operazioni qui riportate usano GPT-6 Luna. Il titolo della chat è incluso.

| Operazione | Token ingresso | Token uscita | USD registrati |
| --- | ---: | ---: | ---: |
| Ciclo chat | 182.704 | 149.161 | $0,09243996 |
| Riformulazione semantica | 555 | 7 | $0,000059 |
| Filtro temporale | 1.182 | 10 | $0,0001232 |
| Espansione parole chiave | 337 | 14 | $0,0000407 |
| Selezione sezioni | 64.051 | 90 | $0,0064501 |
| Classificazione contesto | 71.398 | 130 | $0,0066801 |
| Titolo chat | 255 | 7 | $0,000029 |
| **Totale** | **320.482** | **149.419** | **$0,10582206** |

L'ingresso totale include **10.396 token letti dalla cache**. Le scritture della cache sono zero.
Il ricalcolo con le tariffe Standard coincide con `cost_cents`: circa **10,58 centesimi di dollaro**.
È il costo calcolato da Onyx, non una verifica della fattura OpenAI.
Al [cambio BCE del 2 ottobre 2026](https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml), 1 EUR = 1,1225 USD.
Il totale equivale a circa **€0,09427**, escluse eventuali imposte e commissioni.
La somma degli ingressi supera 272.000 token, ma nessuna chiamata osservata supera quella soglia.
Non abbiamo quindi applicato la maggiorazione per contesto lungo.

### Perché la schermata mostrava ancora «Reading»

La prima ricerca aveva terminato il lavoro. L'attesa lunga era nella successiva chiamata al modello.
Il browser non aveva ricevuto una risposta finale durante quell'attesa.

I parametri salvati mostrano `reasoning_effort=auto`, inviato come `reasoning.effort=medium`, e `max_tokens=128000`.
Una singola chiamata ha registrato **146.528 token di uscita**, non una risposta visibile di quella lunghezza.
I dati disponibili non separano il ragionamento dagli altri token di uscita.
Il numero supera il `max_tokens` salvato: occorre verificare il conteggio del provider e dell'adattatore.

Dopo l'attesa, i log riportano:

```text
Tool call error for internal_search: Missing required 'queries' parameter in internal_search tool call
```

Il ciclo ha poi eseguito altre due ricerche. Questo spiega parte dell'aumento dei consumi successivi.
Non abbiamo ancora identificato perché il modello abbia prodotto quell'uscita o la chiamata non valida.
Non trattare i messaggi tecnici «LLM packet is empty» come prova autonoma del guasto.
Anche i normali pacchetti finali e i pacchetti usage possono essere privi di contenuto.

Il primo test ha mostrato la necessità di controllare ragionamento, uscita e tentativi.
L'utente ha poi scelto una prova con Low, senza modificare il limite di uscita.
Non usare questo test anomalo come costo medio del servizio.

Gli artefatti di sessione sono in `/tmp/wiki-copilot-live-cost.nsnvDQ/`: `before.json`, `after-stop.json` e log API.
Non sono file permanenti del repository. Non pubblicare cookie, credenziali o contenuti riservati.

## Test completo: «Listino Athena», ragionamento Low

L'utente ha inviato «Listino Athena» in una nuova chat autorizzata.
Non abbiamo applicato il limite proposto di 4.096 token né modificato la ricerca o le ACL.

- Baseline: 3 ottobre 2026, 10:17:28 UTC.
- Avvio della domanda: 10:18:58 UTC.
- Prima risposta: circa 8 secondi dopo l'avvio.
- Fine della chiamata finale e dati usage: circa 10:19:09 UTC, dopo circa 11 secondi.
- Verifica successiva: 10:21:44 UTC.
- Parametri effettivi salvati: modello `gpt-6-luna`, effort `low`, `max_tokens=128000`.
- Stream: `done=true`, `truncated=false`, fonti Wiki presenti, nessun pacchetto di errore.
- Chiamata finale al modello: `finish_reason=stop`, non esaurimento del limite.

Il database contiene una sola nuova domanda dello stesso utente dopo la baseline.
Abbiamo sottratto i contatori della baseline da quelli successivi, includendo tutte le operazioni attribuibili.
Tutte le operazioni usano GPT-6 Luna. Il titolo della chat è incluso.

| Operazione | Token ingresso | Token uscita | USD registrati |
| --- | ---: | ---: | ---: |
| Ciclo chat | 27.173 | 260 | $0,0028473 |
| Riformulazione semantica | 550 | 7 | $0,0000585 |
| Filtro temporale | 1.176 | 10 | $0,0001226 |
| Espansione parole chiave | 332 | 20 | $0,0000432 |
| Selezione sezioni | 21.087 | 34 | $0,0021257 |
| Classificazione contesto | 24.339 | 50 | $0,0024589 |
| Titolo chat | 522 | 10 | $0,0000572 |
| **Totale** | **75.179** | **391** | **$0,0077134** |

Letture e scritture della cache: zero. Non abbiamo applicato sconti di cache.
Il ricalcolo delle tariffe Standard coincide con `cost_cents` per ogni operazione.
Al cambio BCE del 2 ottobre, il totale è **€0,0068716258**, circa **0,687 centesimi di euro**.
È il costo calcolato da Onyx, non una verifica della fattura OpenAI.

Il costo è circa 13,7 volte inferiore a quello del primo test anomalo.
La domanda è però diversa: non attribuire tutta la differenza al solo cambio di ragionamento.
La risposta completata non costituisce una verifica completa della sua qualità o dei permessi.
Questo è un caso misurato, non ancora la media di produzione.

Artefatti: `low-test-before.json`, `low-test-after.json`, `low-test-result.json` e `api-log-low-test.txt`
in `/tmp/wiki-copilot-live-cost.nsnvDQ/`.

## Scenari di preventivo

Ipotesi: tutte le chiamate incluse usano Luna. Ingresso e uscita sono **somme sull'intero messaggio utente**.
Le quantità sotto sono ipotesi di carico, non risultati del retrieval dell'esempio Athena.

Costo in USD = (token ingresso × 0,10 + token uscita × 0,50) / 1.000.000.

| Scenario | Ingresso totale | Uscita totale, incluso ragionamento | USD/richiesta | USD/1.000 richieste |
| --- | ---: | ---: | ---: | ---: |
| Leggero | 15.000 | 1.000 | $0,002 | $2 |
| Centrale | 40.000 | 2.000 | $0,005 | $5 |
| Ampio | 100.000 | 10.000 | $0,015 | $15 |

Per un preventivo iniziale, usare **$0,01 per messaggio**: $10 ogni 1.000 messaggi.
È un valore di pianificazione, non una media misurata o un limite garantito.
Conversazioni lunghe, nuove ricerche, maggiore ragionamento e tentativi ripetuti possono superarlo.
Un chiarimento seguito dalla risposta dell'utente conta come due messaggi, con costi separati.

Sono esclusi hosting, indicizzazione iniziale, eventuali embedding a pagamento, strumenti esterni, audio e imposte.
La ricerca interna non è lo strumento OpenAI File Search: non aggiungere automaticamente la sua tariffa per chiamata.

## Come ottenere una misura

Su un ambiente funzionante, eseguire richieste rappresentative con modello ed effort fissati.
Raccogliere tutti gli span della richiesta, inclusi ricerca, selezione, espansione e titolo della chat.
Sommare ingresso non cached, letture/scritture della cache e uscita per modello e tariffa.
Riportare media e percentile 95, distinguendo primo messaggio e messaggi successivi.

Il processore [`user_usage_processor.py`](../../backend/onyx/tracing/processors/user_usage_processor.py)
registra già consumi per modello e operazione.
[`user_usage.py`](../../backend/onyx/db/user_usage.py) li aggrega per utente e intervallo temporale:
non è un registro separato per singola richiesta. Per isolare una richiesta servono i suoi span o una prova senza concorrenza.

## Limite di uscita proposto, non applicato

L'utente ha impostato Low nel pannello del modello.
Il controllo del server mostra `reasoning_effort_max=low`; il valore predefinito nel database resta vuoto.
[`resolve_reasoning_effort`](../../backend/onyx/llm/models.py) limita comunque Auto a Low quando il massimo è Low.
Il limite è quindi effettivo anche senza un valore predefinito esplicito.

Il pannello OpenAI corrente non contiene un campo per il massimo dei token di uscita.
Esiste però una configurazione di distribuzione già supportata: `LITELLM_EXTRA_BODY`.
Per l'attuale percorso OpenAI Responses, proporre inizialmente:

```yaml
LITELLM_EXTRA_BODY: '{"max_output_tokens":4096}'
```

Aggiungere la voce alle variabili del servizio `api_server`, mantenendo quelle esistenti.
Ricreare il container tramite aggiornamento dello stack. Un semplice riavvio non applica nuove variabili Docker.
È un'impostazione globale per le chiamate LLM di quel servizio, non soltanto per una chat.
Verificare la compatibilità prima di usarla con altri provider.

Abbiamo verificato la trasformazione nel container corrente con un trasporto HTTP simulato.
La richiesta intercettata era `POST /v1/responses`, con effort `low` e `max_output_tokens=4096`.
Il controllo ha bloccato la richiesta prima della rete. Non ha consumato token API.
Non abbiamo applicato la variabile né ricreato il container.

Il limite include ragionamento e risposta visibile, per ciascuna chiamata al modello.
Non è un tetto di token o denaro per tutta la richiesta Onyx, che può eseguire molte chiamate.
`GEN_AI_NUM_RESERVED_OUTPUT_TOKENS` riserva spazio minimo: non è un limite massimo di uscita.
Con l'override nel corpo HTTP, il `max_tokens` nominale salvato da Onyx può restare più alto.
Verificare il parametro effettivo inviato, non soltanto quel valore nominale.

L'utente ha preferito verificare il consumo con Low prima di imporre altri limiti.
Il test completo riportato sopra ha quindi usato il limite originale, senza l'override di 4.096 token.

## Previsione annuale per persona e per 80 utenti

Queste sono ipotesi di pianificazione, non statistiche misurate.
Usiamo **220 giorni operativi all'anno**, considerando ferie e festività.
La stima iniziale mensile usava 22 giorni: non la moltiplichiamo per 12 per ottenere 264 giorni operativi.
Le medie mensili sotto sono il totale annuale diviso per 12.

Per una prima previsione usiamo il costo della richiesta completa: **€0,0068716258**.
Manteniamo tariffe e cambio attuali. Non prevediamo i loro cambiamenti durante l'anno.
Una richiesta è un messaggio utente con tutta la pipeline associata.
Ogni successivo messaggio nella stessa chat conta come un'altra richiesta.

L'utente ha chiesto di aumentare il numero di richieste previsto per persona.
La previsione aggiornata considera **20–50 richieste per utente nei giorni di utilizzo**.
Ogni messaggio di chiarimento o approfondimento conta come una richiesta distinta.
Questo intervallo è un'ipotesi di pianificazione, non una frequenza osservata.

Per una persona che usa il servizio in tutti i 220 giorni operativi:

Costo annuo per persona = richieste per giorno operativo × 220 × costo della richiesta completa.

| Richieste/giorno | Richieste/anno per persona | EUR/anno per persona |
| --- | ---: | ---: |
| 0 | 0 | €0,00 |
| 5 | 1.100 | €7,56 |
| 10 | 2.200 | €15,12 |
| 20 | 4.400 | €30,24 |
| 30 | 6.600 | €45,35 |
| 50 | 11.000 | €75,59 |

Per una persona che non usa il servizio ogni giorno, usare i suoi giorni effettivi al posto di 220.
Per 80 utenti, manteniamo giorni senza utilizzo e aumentiamo le richieste per utente attivo:

| Uso | Utenti attivi/giorno | Richieste per utente attivo | Richieste/anno totali | EUR/anno totali | EUR/anno medi per persona | EUR/mese medi totali |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Sostenuto | 32, pari al 40% | 20 | 140.800 | €967,52 | €12,09 | €80,63 |
| Centrale | 32, pari al 40% | 30 | 211.200 | €1.451,29 | €18,14 | €120,94 |
| Molto intenso | 48, pari al 60% | 50 | 528.000 | €3.628,22 | €45,35 | €302,35 |
| Tutti, ogni giorno | 80, pari al 100% | 50 | 880.000 | €6.047,03 | €75,59 | €503,92 |

Lo scenario centrale equivale a 12 richieste medie per persona per giorno operativo, includendo i giorni senza uso.
La media per persona distribuisce il consumo di tutto il gruppo: non è il costo di ogni individuo.
L'ultima riga è uno scenario di uso elevato, non la previsione centrale.

Un margine di pianificazione del 30% porta lo scenario centrale a **€1.886,67/anno**.
Arrotondare a **€1.900/anno** offre un primo budget API per il gruppo, non un tetto garantito.
Il margine è una scelta di preventivo, non un intervallo statistico di confidenza.

Le conversazioni più lunghe possono aumentare il costo medio: il costo della prova breve può sottostimarle.
Con 211.200 richieste annue, una media di €0,01 produrrebbe €2.112/anno; una media di €0,02 produrrebbe €4.224/anno.
Queste due medie sono ipotesi di sensibilità, non nuove misure o prezzi garantiti.

Le cifre escludono hosting, hardware, indicizzazione, strumenti esterni, imposte e commissioni.
Una sola domanda breve non dimostra il costo medio di domande lunghe o conversazioni con molti messaggi.
Includere nel costo medio anche richieste fallite e tentativi, perché possono consumare token.
Un piccolo campione successivo di domande rappresentative richiede un'approvazione separata.
Usare la media misurata per il preventivo e i casi più costosi per controllare il rischio.

## Audit dei consumi del 3 ottobre

L'utente segnala circa $9 nel pannello OpenAI.
Abbiamo controllato contatori e log esistenti, senza nuove chiamate ai modelli.
La lettura del database alle 10:43:49 UTC registra **$7,77676276** dalla mezzanotte UTC.

| Modello | Domande chat osservate | USD registrati |
| --- | ---: | ---: |
| GPT-5.6 Sol | 7 | $7,0121992 |
| GPT-5.6 Luna | 12 | $0,6510281 |
| GPT-6 Luna | 2, una interrotta e una completata | $0,11353546 |
| **Totale** | **21** | **$7,77676276** |

Sol rappresenta circa **90,17%** del totale registrato.
Non possiamo però riconciliare tutti i $9 senza il dettaglio OpenAI per periodo, modello e progetto.
La differenza rispetto a $9 esatti è circa $1,22. Il totale riferito dall'utente è approssimativo.
Non attribuire questa differenza a un modello, a un errore o all'indicizzazione senza altri dati.

### Effetto dei prezzi

Il [listino ufficiale GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol) indica $4/M in ingresso e $20/M in uscita.
GPT-6 Luna costa $0,10/M in ingresso e $0,50/M in uscita.
A parità di token e condizioni Standard, Sol costa **40 volte** GPT-6 Luna.
Anche i prezzi di lettura della cache hanno questo rapporto: $0,40/M contro $0,01/M.

Ricalcolando soltanto il prezzo dei token Sol con quello di GPT-6 Luna, $7,01 diventerebbero circa **$0,1753**.
È un confronto matematico, non un test: non dimostra uguali token, qualità o comportamento cambiando modello.

Sol ha registrato **$3,737298** nel ciclo chat e **$3,2689412** nella ricerca e selezione.
Il resto è il titolo della chat. Il costo non riguarda soltanto la risposta finale.

### Effetto del carico della pipeline

I contatori Sol includono 1.753.562 token in ingresso per le sette domande osservate.
La media contabile è circa 250.509 token in ingresso per domanda, sull'intera pipeline.
Il test completo Athena ne aveva 75.179: non rappresenta quindi tutto il carico osservato oggi.

Una richiesta Sol ha eseguito **sei chiamate del ciclo chat e cinque ricerche interne**.
I soli cicli chat hanno consumato 504.520 token in ingresso e circa **$2,0394**.
Questa cifra esclude le operazioni secondarie di ricerca e selezione.
I dati dimostrano un costo da chiamate multiple e prompt grandi, non necessariamente un errore del codice.

Anche con Luna il costo varia: le dodici domande GPT-5.6 Luna totalizzano $0,6510, circa $0,0543 ciascuna.
Non sono lo stesso modello o la stessa configurazione del test GPT-6 Luna Low.
Il test anomalo GPT-6 Luna da $0,1058 mostra inoltre che il prezzo del modello non basta a garantire il costo.

**Conclusione:** Sol spiega la maggior parte della spesa registrata, ma non possiamo dichiarare che sia l'unico fattore.
Ricerche multiple, contesto e ragionamento incidono sul costo e sulla variabilità per richiesta.
Le previsioni annuali basate su Athena restano preliminari.
Il carico medio Sol, ricalcolato ai prezzi GPT-6 Luna, varrebbe circa €0,0223 per domanda.
È circa 3,25 volte il test Athena, anche senza il prezzo Sol; non è una nuova misura GPT-6 Luna.

Per riconciliare il pannello, chiedere un export dei consumi OpenAI con periodo, modelli e progetti, senza chiavi API.
Artefatti locali: `day-audit.json`, `day-tool-metadata.json` e `api-log-day.txt` nella directory temporanea della sessione.
