# secon.github.io

Archivio statico di conferenze (Jekyll + tema Cayman, pubblicato con GitHub Pages).

## Struttura

- `conferences/<slug>.yml` — i dati della conferenza (una per file).
- `conferences/<slug>.html` — pagina della conferenza; contiene solo `layout: conference`.
- `_layouts/conference.html` — renderizza il YAML in HTML.
- `index.html` — elenco di tutte le conferenze, ordinate per anno.
- `_templates/conference.yml` — template da copiare per una nuova conferenza.

## Aggiungere una conferenza

1. Copia `_templates/conference.yml` in `conferences/<slug>.yml` (es. `weis2024.yml`) e compilalo.
2. Crea `conferences/<slug>.html` con questo contenuto:

   ```
   ---
   layout: conference
   ---
   ```

3. Commit e push: GitHub Pages ricostruisce il sito.

Nota: il file `.yml` non deve iniziare con `---`, altrimenti Jekyll lo tratta come una pagina.

## Build locale

```
export PATH="/opt/homebrew/opt/ruby/bin:$PATH"   # Ruby >= 3.0
bundle install
bundle exec jekyll serve
```

Poi apri http://localhost:4000.
