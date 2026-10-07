# secon.github.io

Archivio statico di conferenze (Jekyll + tema Cayman, pubblicato con GitHub Pages).

## Struttura

- `index.html` — pagina principale: per ogni conferenza le info generali e l'elenco dei paper (con link al file, o "not available").
- `conferences/papers/<slug>.yml` — elenco paper di una conferenza (alimenta la pagina principale). Formato in `_templates/papers.yml`.
- `papers/<slug>/` — i file dei paper, nominati `<slug>_NN_<titolo>.pdf`.
- `conferences/yml/<slug>.yml` — programma completo della conferenza (opzionale, una per file).
- `conferences/pages/<slug>.html` — pagina del programma; contiene solo `layout: conference`.
- `_layouts/conference.html` — renderizza il programma in HTML.
- `_templates/` — template da copiare per una nuova conferenza.

## Aggiungere una conferenza (elenco paper)

1. Copia `_templates/papers.yml` in `conferences/papers/<slug>.yml` (es. `weis2027.yml`) e compila le info generali.
2. Metti i file in `papers/<slug>/` con nome `<slug>_NN_<titolo>.pdf`.
3. Elenca i paper nel yml (id, title, authors, file, path). Per i paper non disponibili lascia `file: null` e `path: null`.
4. Commit e push: la pagina principale si aggiorna da sola.

Se esiste il programma completo (`conferences/yml/<slug>.yml`) il file si genera in automatico:

```
python3 scripts/build_papers_yml.py            # tutte le conferenze
python3 scripts/build_papers_yml.py weis2027   # solo una
```

## Aggiungere il programma completo (opzionale)

1. Copia `_templates/conference.yml` in `conferences/yml/<slug>.yml` (es. `weis2024.yml`) e compilalo.
2. Crea `conferences/pages/<slug>.html` con questo contenuto:

   ```
   ---
   layout: conference
   ---
   ```

3. Commit e push: GitHub Pages ricostruisce il sito.

Nota: i file `.yml` non devono iniziare con `---`, altrimenti Jekyll li tratta come pagine.

## Build locale

```
export PATH="/opt/homebrew/opt/ruby/bin:$PATH"   # Ruby >= 3.0
bundle install
bundle exec jekyll serve
```

Poi apri http://localhost:4000.
