# Deploy con GitHub Actions spezzato in chunk

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
