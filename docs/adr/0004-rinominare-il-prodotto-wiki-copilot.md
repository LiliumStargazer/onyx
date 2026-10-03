# Riutilizzare il nome Wiki Copilot per il nuovo prodotto

Wiki Agent Rag (`wiki-agent-rag`), il fork di Onyx, prende il nome Wiki Copilot (`wiki-copilot`). Il progetto precedente diventa Wiki Copilot legacy (`wiki-copilot-legacy`), senza archiviazione o modifiche ai suoi file. Così il nuovo prodotto conserva il nome noto agli utenti e resta distinto dal precedente. Decisione: [#27](https://github.com/LiliumStargazer/wiki-copilot/issues/27).

Il nuovo prodotto non è in produzione: rinominiamo anche gli identificatori interni, senza compatibilità con i nomi precedenti. L'icona originale usa un anello grigio spesso, l'interno bianco e una W grigia; non usa i marchi Wikimedia.

## Distribuzione

Lo stack Portainer `wiki-agent-rag` (id 27) mantiene il nome. Compose lo usa come prefisso dei volumi: rinominarlo creerebbe volumi vuoti e conflitti con i volumi `wiki-copilot_*`. Il suo URL Git `wiki-agent-rag.git` continua a funzionare tramite il redirect GitHub.

Rinominiamo prima il repository legacy e i suoi remote. Solo dopo assegniamo `wiki-copilot` al fork: GitHub elimina il redirect precedente quando un altro repository prende quel nome. L'operatore ha eliminato lo stack legacy `wiki-copilot` (id 12) prima della rinomina.

Il push su `main` esegue i controlli, ma non pubblica immagini. L'operatore sceglie il prossimo tag `v1.0.N` per distribuire il nuovo nome e l'icona. Il workflow permette anche la pubblicazione manuale.
