# Deploy con GitHub Actions spezzato in chunk

## Nuovo scraper PESDB 2027

Usa `.github/workflows/weekly-standard-pesdb-2027.yml`.

Il workflow acquisisce solo i giocatori con filtro PESDB `availability=standard`.
Ha due punti di conferma: dopo la raccolta del catalogo e prima della pubblicazione.

Per rendere effettive le conferme, in GitHub crea due Environments e imposta i
required reviewers:

- `pesdb-scrape-discovery-approval`
- `pesdb-scrape-publish-approval`

Senza required reviewers gli Environment non bloccano il workflow. Per il primo
run seleziona `Run workflow`, modalita `full`; per i run successivi usa
`incremental`. Il campo `max_pages` serve solo a provare la pipeline su un
campione ridotto. Quando `max_pages` contiene un valore, il workflow completa
la verifica tecnica ma non pubblica mai il dataset parziale nel repository.

La discovery iniziale delle 784 pagine Standard e volutamente limitata a una
richiesta ogni 2,5 secondi, per evitare i rate limit di PESDB. Può richiedere
circa 30-45 minuti. Se PESDB risponde con rate limit il workflow termina subito
con un messaggio chiaro, senza accumulare attese di molti minuti.

Questa e' la soluzione migliore possibile senza dipendere da un tuo PC acceso:

1. un job GitHub estrae tutti gli ID;
2. divide gli ID in blocchi;
3. una matrix di job processa i blocchi in parallelo;
4. un job finale unisce tutto;
5. i file finali vengono salvati nel repository:
   - `data/pesdb_players_it.json`
   - `data/pesdb_players_meta.json`

## Perche' questa soluzione

- evita un job unico da 16 ore;
- sfrutta il parallelismo di GitHub Actions;
- permette alla tua app Vercel di vedere JSON e metadata dopo il push finale.

## Limiti

- su repository privati, GitHub Free ha minuti limitati;
- i job hosted hanno limite massimo di durata per job;
- se il numero di giocatori cresce molto, potresti comunque dover aumentare il `chunk_size` o ridurre il parallelismo.

## Workflow

Il workflow e' in:

- `.github/workflows/weekly-chunked-scrape.yml`

Parte:

- ogni domenica alle 02:00 UTC
- oppure manualmente da `Actions > Run workflow`

## Output finali

- `data/pesdb_players_it.json`
- `data/pesdb_players_meta.json`

Il file metadata contiene:

- data run
- numero giocatori
- numero ID
- colonne presenti
- celle vuote per colonna
- errori raccolti dai chunk

## Modifica dimensione chunk

Nel file `scraping_pesdb_unificato.py` trovi:

- `CHUNK_SIZE = 250`

Se necessario puoi aumentarlo o ridurlo.
