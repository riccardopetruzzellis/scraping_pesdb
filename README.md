# Scraping PESDB

Questo progetto ora usa un solo script:

`scraping_pesdb_unificato.py`

Il flusso e':

1. apre tutte le pagine elenco di PESDB e raccoglie gli ID;
2. visita ogni scheda giocatore;
3. salva un CSV grezzo;
4. traduce intestazioni e valori usando `file_modifiche.xlsx`;
5. elimina le colonne indicate in `file_modifiche.xlsx` e quelle di default;
6. salva il JSON finale.

Per default non usa piu' un `END_PAGE` fisso: parte da `START_PAGE` e si ferma quando incontra pagine senza giocatori per due volte di seguito.

## File generati

Nella cartella `output` vengono creati:

- `player_ids.txt`
- `pesdb_players_raw.csv`
- `pesdb_players_it.json`
- `log_pagine.xlsx`
- `log_errori.txt`

## File modifiche

Il file `file_modifiche.xlsx`, foglio `Regole`, viene letto automaticamente:

- colonna `A`: intestazione originale estratta;
- colonna `B`: intestazione finale desiderata;
- colonna `C`: valore originale estratto;
- colonna `D`: valore finale desiderato;
- colonna `E`: nome colonna da rimuovere dall'output finale.

Le regole del file Excel hanno priorita' sui dizionari interni dello script.

La colonna `Player Skills` viene inoltre espansa automaticamente in:

- `Player_Skills_1`
- `Player_Skills_2`
- `Player_Skills_3`
- ...

Il riconoscimento dei valori in `Player Skills` ignora differenze di spazi e underscore tra estrazione e file regole.

## Colonne escluse di default

Lo script rimuove automaticamente:

- `Squad Number:`
- `Permalink:`
- `Forum code:`
- `Facebook:`
- `Twitter:`
- la colonna vuota generata da PESDB

Se vuoi mantenere una colonna esclusa, puoi lanciarlo cosi':

```powershell
python scraping_pesdb_unificato.py --include-column "Squad Number:"
```

## Esecuzione locale

```powershell
pip install -r requirements.txt
python scraping_pesdb_unificato.py
```

Se vuoi limitare il run per test:

```powershell
python scraping_pesdb_unificato.py --end-page 3
```

## Deploy con GitHub Actions

Questo progetto e' pronto per funzionare senza installazioni sui tuoi PC usando GitHub Actions.

Flusso:

1. un job prepara tutti gli ID;
2. gli ID vengono divisi in chunk;
3. piu' job GitHub processano i chunk in parallelo;
4. un job finale unisce tutto e aggiorna:
   - `data/pesdb_players_it.json`
   - `data/pesdb_players_it.csv`
   - `data/pesdb_players_meta.json`
   - `data/pesdb_players_diff.json`
   - `data/history/YYYY-MM-DD/...` per conservare ogni versione

Workflow:

- `.github/workflows/weekly-chunked-scrape.yml`

Guida:

- `DEPLOY_GITHUB_ACTIONS.md`

### Scraping incrementale

Per ridurre tempi ed errori dopo gli aggiornamenti settimanali di PESDB, la pipeline usa lo scraping incrementale.

La lista giocatori viene sempre riletta tutta, cosi' non si perdono nuovi ID. Le schede complete vengono invece scaricate solo quando serve:

- giocatore nuovo;
- giocatore presente nella pagina `Modified Players` dell'ultimo update PESDB, cosi' vengono intercettate anche modifiche interne come statistiche e stile di gioco;
- dati principali cambiati nella lista PESDB: nome, ruolo, squadra, nazione, altezza, peso, eta', overall;
- quota di refresh periodico, per intercettare modifiche non visibili nella lista.

I giocatori invariati vengono riusati dal JSON precedente in `data/pesdb_players_it.json`, mantenendo invariato il formato finale importabile in app.

Variabili utili:

- `PESDB_INCREMENTAL_MODE=0` forza una scansione completa;
- `PESDB_CHANGELOG_MODIFIED_MODE=0` disattiva il refresh forzato dei giocatori presenti in `Modified Players`;
- `PESDB_INCREMENTAL_REFRESH_BUCKETS=4` e' il default: circa un quarto delle schede viene comunque aggiornato a ogni run;
- `PESDB_INCREMENTAL_REFRESH_BUCKETS=1` equivale a riscaricare tutti i dettagli.

### Metadata prodotti

Il file `pesdb_players_meta.json` contiene:

- data generazione
- numero giocatori trovati
- numero ID raccolti
- pagine processate
- elenco colonne
- numero celle vuote per colonna
- flag presenza errori
- numero giocatori aggiunti/rimossi/modificati rispetto al run precedente
- numero giocatori scaricati davvero e riusati da cache nel run incrementale

Questo file serve per mostrare nell'app pubblicata se il run e' andato bene.

## Note

- Lo script salva checkpoint durante l'estrazione dettagli.
- I testi vengono normalizzati per ripulire caratteri speciali, apostrofi tipografici, spazi anomali e accenti composti.
- Le traduzioni possono essere gestite soprattutto da `file_modifiche.xlsx`; i dizionari interni restano come fallback.
- Il passo successivo naturale e' importare il JSON in Supabase dalla tua app admin.
