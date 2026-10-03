# Alternative gratuite a GPT-6 Luna per Wiki Agent Rag

Ricognizione del 3 ottobre 2026. Fonti: documentazione e cataloghi ufficiali.
Non abbiamo eseguito altre chiamate ai modelli, creato account o modificato la configurazione del servizio.

## Esito

**Prima candidata per una prova gratuita: `qwen/qwen3.8-27b:free` tramite OpenRouter.**
Il catalogo offre ingresso e uscita a prezzo zero, strumenti e 262.144 token di contesto.
L'endpoint gratuito ModelRun compare anche nella lista ufficiale Zero Data Retention (ZDR).
Questi dati giustificano una prova, non una scelta di produzione o una promessa di parità con Luna.

**DeepSeek V4 Flash non è un'API gratuita.** I pesi originali permettono l'esecuzione in proprio con licenza MIT.
Il server attuale non può ospitarlo con risorse adeguate.

Non abbiamo trovato una soluzione che garantisca insieme gratuità, qualità equivalente e capacità di produzione per questo caso.
La qualità equivalente richiede una verifica sui documenti, sulle domande e sui ruoli aziendali.

## Requisiti del nostro caso

La pipeline deve cercare nella Wiki, selezionare documenti e restituire risposte italiane con fonti corrette.
Deve gestire chiamate agli strumenti e risposte strutturate, non soltanto scrivere testo.
Il cambio di modello non deve modificare gli utenti, i ruoli o i filtri ACL.

Il [test Athena interrotto](luna-cost-per-user-request.md) ha registrato 320.482 token in ingresso sull'intera pipeline.
La chiamata dopo la prima ricerca aveva circa 21.520 token in ingresso.
Le ricerche successive hanno aumentato il prompt fino a 85.839 token per una chiamata.
Non confondere il carico totale della pipeline con il contesto di una singola chiamata.

Il server osservato ha 2 vCPU e circa 7,6 GiB di RAM.
Non abbiamo rilevato una GPU NVIDIA o AMD da calcolo; il dispositivo video PCI rilevato è quello virtuale Amazon.
La RAM disponibile era circa 1,5 GiB. La swap da 2 GiB era quasi interamente occupata.
Non aggiungere un modello locale pesante a questo host senza una valutazione delle risorse.

## Confronto

| Soluzione | Gratuita? | Valutazione per noi |
| --- | --- | --- |
| Qwen3.8-27B su OpenRouter, variante `:free` | Token gratuiti, con quote | Prima candidata per una prova limitata. Qualità e latenza non verificate sul corpus. |
| Qwen3.8-27B eseguito in proprio | Pesi Apache 2.0; hardware ed energia a carico nostro | Candidata per un servizio controllato, se esiste hardware adeguato. Non sull'host attuale. |
| DeepSeek V4 Flash eseguito in proprio | Pesi MIT; hardware ed energia a carico nostro | Troppo grande per l'host attuale. Non è un piccolo modello da 13B da caricare integralmente. |
| DeepSeek Flash via API ufficiale | No | Servizio a pagamento. Il vecchio nome V4 Flash oggi identifica una versione successiva. |
| Gemma 4 31B su OpenRouter, variante `:free` | Token gratuiti, con quote | Seconda candidata tecnica. L'endpoint gratuito osservato non compare nella lista ZDR. |
| Gemini Flash, quota gratuita | Esiste nel listino | Non raccomandata per il nostro servizio italiano: i termini richiedono Paid Services per utenti SEE. |
| Groq, modelli gratuiti disponibili | Quote gratuite | Limiti osservati da 8.000 token/minuto: insufficienti per il prompt Athena da circa 21.500 token. |
| Cerebras Shared Inference | Solo prova temporanea | Credito di $5 per 30 giorni, con metodo di pagamento verificato. Non è un piano gratuito permanente. |

Le quote e i cataloghi possono cambiare. Verificare di nuovo prezzi e condizioni prima di configurare un provider.

## DeepSeek V4 Flash: API ed esecuzione in proprio

La scheda ufficiale del modello originale indica:

- 284 miliardi di parametri totali;
- 13 miliardi di parametri attivi per token;
- contesto fino a un milione di token;
- pesi scaricabili e licenza MIT;
- istruzioni ufficiali per l'esecuzione locale e distribuita.

I parametri attivi descrivono il calcolo per token, non tutta la memoria necessaria ai pesi.
Anche una stima ideale a 4 bit richiede circa 142 GB per 284 miliardi di parametri.
Questa è una stima dei soli pesi, non una misura della memoria effettiva del servizio.
Occorre aggiungere metadati, cache, memoria di lavoro e richieste concorrenti.

Il listino API ufficiale corrente usa `deepseek-flash`, servito da **DeepSeek V4.1 Flash**.
Accetta ancora `deepseek-v4-flash`, ma specifica che il modello corrispondente è stato ritirato.
L'alias oggi usa V4.1 Flash e le sue tariffe.
Non confondere i pesi originali scaricabili con il modello servito dall'alias API.

Prezzi ufficiali correnti, USD per milione di token:

| Tipo | Fascia ridotta | Fascia di punta |
| --- | ---: | ---: |
| Ingresso senza cache | $0,15 | $0,30 |
| Ingresso con cache | $0,003 | $0,006 |
| Uscita | $0,60 | $1,20 |

Sono prezzi a pagamento, non un'alternativa gratuita a Luna.
L'API supporta strumenti, JSON e modalità senza ragionamento.
Il ragionamento è però attivo per impostazione predefinita, con effort `high`.
Un cambio di modello senza controllare questa impostazione può riprodurre attese e consumi elevati.

Fonti: [pesi V4 Flash](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash),
[esecuzione locale](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash/blob/main/inference/README.md),
[listino API](https://api-docs.deepseek.com/quick_start/pricing),
[controllo del ragionamento](https://api-docs.deepseek.com/guides/thinking_mode).

## Qwen3.8-27B: perché provarlo per primo

La scheda ufficiale indica 27 miliardi di parametri, licenza Apache 2.0 e contesto nativo da 262.144 token.
Descrive miglioramenti nell'esecuzione degli strumenti e nel rispetto delle istruzioni.
Questi risultati del produttore non dimostrano la qualità sul nostro RAG italiano.

OpenRouter espone una variante gratuita con strumenti e risposte strutturate.
L'endpoint osservato è **ModelRun**, con quantizzazione FP4 e prezzo zero per ingresso e uscita.
Compare nella [lista ZDR ufficiale](https://openrouter.ai/api/v1/endpoints/zdr).
Il catalogo dichiara `tool_choice=auto`, `required` e funzione esplicita, ma non `none`.
Verificare anche la chiusura del ciclo strumenti nella prova con Onyx.

Le quote gratuite documentate sono:

- 20 chiamate al minuto;
- 50 chiamate al giorno senza acquisti di crediti sufficienti;
- 1.000 chiamate al giorno dopo acquisti di crediti per circa $10, secondo la soglia documentata.

L'ultima opzione richiede denaro: non soddisfa una richiesta di gratuità assoluta.
Le quote contano **chiamate al modello**, non messaggi utente.
Un messaggio Onyx può consumare molte chiamate tra ricerca, classificazione, risposta e titolo.
Non presentare 50 chiamate come 50 domande complete.

Onyx contiene già i provider OpenRouter, Ollama e OpenAI-compatible.
Non serve progettare un nuovo backend solo per valutare queste alternative.
La disponibilità del provider non dimostra che tutti i parametri del nuovo modello funzionino correttamente.

Anche Qwen ragiona per impostazione predefinita. La documentazione permette di disabilitare il ragionamento.
Il parametro dipende dall'endpoint: verificare la traduzione applicata da Onyx e dal provider.

Per l'esecuzione in proprio, 27B a 4 bit richiede almeno circa 13,5 GB per i soli pesi.
Una GPU da 24–32 GB è una prima ipotesi da valutare con contesto limitato, non una garanzia di capacità.
Il contesto lungo e le richieste concorrenti possono richiedere più memoria.
Non abbiamo eseguito prove hardware.

Fonti: [scheda Qwen](https://huggingface.co/Qwen/Qwen3.8-27B),
[catalogo OpenRouter](https://openrouter.ai/api/v1/models),
[endpoint gratuito](https://openrouter.ai/api/v1/models/qwen/qwen3.8-27b:free/endpoints),
[quote](https://openrouter.ai/docs/api-reference/limits),
[sorgente delle quote](https://openrouter.ai/docs/api-reference/limits.md),
[privacy](https://openrouter.ai/docs/guides/privacy/data-collection),
[regole ZDR](https://openrouter.ai/docs/guides/features/zdr).

## Perché non scegliere subito le altre API gratuite

**Gemini:** il listino espone token gratuiti anche per Gemini 3.8 Flash.
I termini richiedono però Paid Services per applicazioni rese disponibili a utenti SEE, Svizzera e Regno Unito.
I termini definiscono Paid Services API tramite un progetto con fatturazione attiva.
La protezione dei dati per utenti SEE non elimina quel requisito contrattuale.
Non basare il servizio aziendale italiano sull'idea «Gemini API gratis» senza chiarire condizioni e fatturazione.

**Groq:** i modelli testuali principali osservati, compreso Qwen3.8-27B, hanno una quota di 8.000 token/minuto.
Il prompt Athena dopo la ricerca supera quella quota già da solo.
Ridurre il contesto e cambiare il lavoro di selezione sarebbe una modifica della pipeline, non una sostituzione diretta.

**Cerebras:** le condizioni correnti dichiarano esplicitamente che non esiste un piano gratuito permanente.
Il credito iniziale richiede un metodo di pagamento e scade dopo 30 giorni.

**Gemma 4 e Nemotron gratuiti su OpenRouter:** sono alternative tecniche possibili.
Gli endpoint gratuiti esaminati non compaiono nella lista ZDR rilevata.
Non sceglierli per inviare listini riservati soltanto perché il prezzo dei token è zero.

Fonti: [Gemini prezzi](https://ai.google.dev/gemini-api/docs/pricing),
[Gemini termini](https://ai.google.dev/gemini-api/terms),
[Groq quote](https://console.groq.com/docs/rate-limits),
[Cerebras quote e prova](https://inference-docs.cerebras.ai/support/rate-limits),
[Gemma 4](https://huggingface.co/google/gemma-4-31B-it),
[endpoint Gemma gratuito](https://openrouter.ai/api/v1/models/google/gemma-4-31b-it:free/endpoints).

## Verifica proposta, non eseguita

Prima della prova, approvare il provider e le condizioni per i dati aziendali.
ZDR descrive la conservazione dei contenuti. Non sostituisce la verifica del contratto e del trattamento dei dati.

1. Usare solo un modello con prezzo zero, senza passaggio automatico a modelli a pagamento.
2. Controllare tutti i flussi, compreso il titolo della chat. Mantenere locali gli embedding esistenti.
3. Impostare limiti di uscita e tentativi adatti a una ricerca documentale, non al massimo teorico del modello.
4. Verificare prima il comportamento senza ragionamento, la cancellazione e gli errori di quota.
5. Provare 8–10 domande note: listini, versioni, collegamenti, ambiguità, documento assente e accesso negato.
6. Confrontare con risposte attese verificate sui documenti, senza usare un altro modello a pagamento come giudice.
7. Misurare qualità, fonti, errori degli strumenti, tempo totale e chiamate per messaggio su tutta la pipeline.

La domanda di scelta hardware resta aperta: esiste già un PC o server aziendale con una GPU adeguata?
Se esiste, valutare Qwen eseguito in proprio. Altrimenti, la prova gratuita con OpenRouter è il primo passo possibile.
Non abbiamo aperto una mappa Wayfinder: questa ricognizione era completabile in una sessione.
Una mappa diventa utile se decidiamo di progettare e gestire un nuovo servizio di inferenza.
