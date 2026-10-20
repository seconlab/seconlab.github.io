# Aggiungere una conferenza con paper gia' disponibili

Questa procedura parte dai PDF che possiedi gia': non serve cercare paper online,
scaricarli o creare una copia del sito della conferenza.

Negli esempi la nuova conferenza e' **WEIS 2027**, con identificativo `weis2027`.
Per gli anni successivi sostituisci anno e identificativo in tutti i percorsi.
Esegui i comandi dalla cartella principale del repository.

## 1. Copia i PDF nell'archivio

Crea la cartella:

```sh
mkdir -p papers/weis2027
```

Copia qui i PDF e assegna nomi semplici, senza spazi, per esempio:

```text
papers/weis2027/weis2027_01_primo-paper.pdf
papers/weis2027/weis2027_02_secondo-paper.pdf
```

Usa numeri progressivi distinti e non cambiare i nomi dei paper gia' pubblicati,
per non interrompere i collegamenti esistenti.

## 2. Crea l'elenco della conferenza

Copia il modello:

```sh
cp _templates/papers.yml conferences/papers/weis2027.yml
```

Modifica `conferences/papers/weis2027.yml` con i metadati reali e una voce per
ogni PDF. Esempio minimo completo:

```yaml
name: "WEIS 2027"
year: 2027
papers:
- id: weis2027_01
  title: "Titolo del primo paper"
  authors:
  - name: "Nome Cognome"
    affiliation: "Universita' o istituzione"
  - name: "Nome Secondo Autore"
    affiliation: "Altra istituzione"
  file: weis2027_01_primo-paper.pdf
  path: papers/weis2027/weis2027_01_primo-paper.pdf
- id: weis2027_02
  title: "Titolo del secondo paper"
  authors:
  - name: "Nome Terzo Autore"
  file: weis2027_02_secondo-paper.pdf
  path: papers/weis2027/weis2027_02_secondo-paper.pdf
```

- `name` e `year` identificano la conferenza nella homepage e nelle statistiche.
- `papers` contiene tutti i paper della conferenza; elimina le voci di esempio
  rimaste dal modello.
- `id` deve essere univoco: identificativo della conferenza e numero del paper.
- `file` e' il nome esatto del PDF, estensione inclusa.
- `path` e' il percorso relativo alla radice del repository, senza `/` iniziale.
  Rispetta maiuscole e minuscole: il sito pubblicato le distingue.
- Inserisci tutti gli autori in `authors`, uno per voce; `affiliation` e'
  facoltativo. Mantieni lo stesso nome usato negli altri anni: le statistiche
  non uniscono automaticamente varianti ortografiche o iniziali diverse.
- Se mancano dati come sede, date o sito web, elimina i valori di esempio del
  modello. Puoi aggiungere `full_name`, `edition`, `location`, `venue`,
  `start_date`, `end_date` e `website` quando li conosci. Scrivi le date
  come `"2027-06-01"`.
- Non aggiungere `---` all'inizio del file YAML: e' un file dati, non una pagina.
- Usa spazi, non tabulazioni, per l'indentazione. Racchiudi i titoli tra
  virgolette, soprattutto se contengono `:` o `#`.
- Se un paper non ha ancora il PDF, usa `file: null` e `path: null`; comparira'
  comunque nell'elenco e nelle statistiche.

**Non servono** file in `conferences/yml/`, `conferences/pages/` o `papers/yml/`,
ne' modifiche a `conferences/websites.yml`. La homepage legge direttamente
`conferences/papers/*.yml` e aggiunge automaticamente la nuova conferenza.

**Non eseguire** `download_papers.py` o `mirror_websites.py` per questa procedura.
Non eseguire neppure `build_papers_yml.py` per la conferenza compilata a mano:
quello script usa il programma in `conferences/yml/` e puo' sovrascrivere
l'elenco manuale.

## 3. Aggiorna le statistiche

```sh
python3 scripts/update_stats.py
```

Servono i pacchetti Python `pandas` e `pyyaml`. Lo script rigenera
`stats/index.html`, includendo i nuovi autori e paper nella pagina `/stats`.
Le presenze indicano le edizioni con almeno un paper dell'autore, non la
partecipazione fisica alla conferenza.

## 4. Controlla il sito in locale

Con Ruby e le dipendenze del progetto disponibili:

```sh
bundle exec jekyll serve
```

Su un Mac con Ruby installato tramite Homebrew, se il comando usa il vecchio
Ruby di sistema:

```sh
export PATH="/opt/homebrew/opt/ruby/bin:$PATH"
bundle exec jekyll serve
```

Apri `http://127.0.0.1:4000/` e controlla:

1. La nuova conferenza compare con anno e titolo corretti.
2. Tutti i paper e gli autori sono presenti.
3. Ogni link al PDF apre il documento giusto.
4. `http://127.0.0.1:4000/stats/` include i nuovi autori e conteggi.

Non modificare `_site/`: e' una cartella generata da Jekyll.
Termina il server con `Ctrl+C`.

## 5. Pubblica

Controlla le modifiche e aggiungi solo i file della nuova conferenza:

```sh
git status --short
git add papers/weis2027/ conferences/papers/weis2027.yml stats/index.html
git commit -m "Add WEIS 2027 papers"
git push
```

Dopo il completamento della pubblicazione GitHub Pages, la conferenza sara'
visibile sul sito. Non serve modificare manualmente `index.html`.

## Aggiungere altri paper a una conferenza esistente

1. Copia i nuovi PDF nella sua cartella `papers/<identificativo>/`.
2. Aggiungi le voci a `conferences/papers/<identificativo>.yml`, senza eliminare
   quelle esistenti e usando nuovi identificativi univoci.
3. Esegui `python3 scripts/update_stats.py`.
4. Controlla i link e pubblica i PDF, il file YAML e `stats/index.html`.