#!/usr/bin/env python3
"""Genera /stats dai paper della homepage: python3 scripts/update_stats.py."""
import json
import unicodedata
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "conferences" / "papers"
OUTPUT = ROOT / "stats" / "index.html"


def build_stats(source):
    files = sorted(source.glob("*.yml"))
    if not files:
        raise ValueError(f"Nessuna conferenza trovata in {source}")

    records = []
    for path in files:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        year = int(data["year"])
        for index, paper in enumerate(data["papers"]):
            for author in paper.get("authors") or []:
                name = " ".join(unicodedata.normalize("NFKC", author["name"]).split())
                if not name:
                    raise ValueError(f"{path}: autore senza nome nel paper {index + 1}")
                records.append({
                    "key": name.casefold(), "author": name,
                    "edition": path.stem, "year": year, "paper": index,
                })
    if not records:
        raise ValueError(f"Nessun autore trovato in {source}")

    frame = pd.DataFrame.from_records(records)
    frame = frame.drop_duplicates(["key", "edition", "paper"])
    grouped = frame.groupby("key", sort=True)
    stats = grouped.agg(
        author=("author", "first"),
        conferences=("edition", "nunique"),
        papers=("paper", "size"),
        first_year=("year", "min"),
        last_year=("year", "max"),
        years=("year", lambda values: ", ".join(map(str, sorted(set(values))))),
    ).reset_index()
    stats = stats.sort_values(
        ["conferences", "papers", "key"], ascending=[False, False, True],
    ).drop(columns="key")
    stats.insert(0, "rank", range(1, len(stats) + 1))
    return json.loads(stats.to_json(orient="records", force_ascii=True))


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WEIS author statistics</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/tabulator-tables@6.3.1/dist/css/tabulator_simple.min.css" rel="stylesheet">
  <style>
    body { background: #fff; color: #30363b; }
    .card, .btn, .form-control, .form-select { border-radius: 0; box-shadow: none; }
    .card { border-color: #d5d9dc; }
    .tabulator { font-size: .9rem; }
    .tabulator .tabulator-header .tabulator-col { background: #f4f5f6; }
    .tabulator-row.tabulator-selected { background: #e2e5e8; }
  </style>
</head>
<body>
  <main class="container-fluid px-3 px-md-5 py-4">
    <a href="../" class="link-secondary">All conferences</a>
    <h1 class="h3 mt-3">WEIS author statistics</h1>
    <p class="text-secondary">
      Ranked by editions with at least one paper, then by paper count.
      This measures authorship, not physical attendance. Names are matched ignoring
      case and repeated whitespace; spelling variants are not merged.
      Rank refers to the complete dataset.
    </p>
    <div class="row g-3 mb-4">
      <div class="col-sm-4"><div class="card h-100"><div class="card-body">
        <div class="text-secondary">Authors (filtered)</div><strong id="author-count">0</strong>
      </div></div></div>
      <div class="col-sm-4"><div class="card h-100"><div class="card-body">
        <div class="text-secondary">Author-paper credits (filtered)</div><strong id="paper-count">0</strong>
      </div></div></div>
      <div class="col-sm-4"><div class="card h-100"><div class="card-body">
        <div class="text-secondary">Most editions (filtered)</div><strong id="edition-count">0</strong>
      </div></div></div>
    </div>
    <p class="small text-secondary">Each coauthor receives one credit per paper, including papers without a downloadable file.</p>
    <fieldset class="mb-3">
      <legend class="fs-6">Visible columns</legend>
      <div id="column-toggles" class="d-flex flex-wrap gap-3"></div>
    </fieldset>
    <div class="d-flex flex-wrap gap-2 mb-3">
      <button id="clear-filters" class="btn btn-outline-secondary btn-sm" type="button">Clear filters</button>
      <button id="download-filtered" class="btn btn-outline-secondary btn-sm" type="button">Download filtered CSV</button>
      <button id="download-all" class="btn btn-outline-secondary btn-sm" type="button">Download all CSV</button>
    </div>
    <p class="small text-secondary">Numeric filters accept &gt;10, &lt;5, &gt;=3, &lt;=20, =2 or !=0. A plain number means equality.</p>
    <div id="stats-table" aria-label="Author ranking"></div>
    <noscript><p>Enable JavaScript to view the author ranking.</p></noscript>
    <p id="stats-error" class="text-danger mt-3" role="alert" hidden></p>
  </main>
  <script id="stats-data" type="application/json">__STATS_DATA__</script>
  <script src="https://cdn.jsdelivr.net/npm/tabulator-tables@6.3.1/dist/js/tabulator.min.js"></script>
  <script>
    if (typeof Tabulator === "undefined") {
      const error = document.getElementById("stats-error");
      error.hidden = false;
      error.textContent = "Unable to load the table library. Check your connection and reload.";
    } else {
      const rows = JSON.parse(document.getElementById("stats-data").textContent);
      function numericFilter(filter, value) {
        const match = String(filter).trim().match(/^(<=|>=|!=|=|<|>)?\\s*(-?\\d+(?:\\.\\d+)?)$/);
        if (!match) return false;
        const number = Number(match[2]);
        switch (match[1] || "=") {
          case "<": return value < number;
          case ">": return value > number;
          case "<=": return value <= number;
          case ">=": return value >= number;
          case "!=": return value !== number;
          default: return value === number;
        }
      }
      function numericColumn(title, field) {
        return {
          title, field, sorter: "number", headerFilter: "input",
          headerFilterFunc: numericFilter, headerFilterPlaceholder: "e.g. >=3",
          minWidth: 110,
        };
      }
      const columns = [
        numericColumn("Rank", "rank"),
        {title: "Author", field: "author", headerFilter: "input", formatter: "plaintext", minWidth: 220},
        numericColumn("Editions", "conferences"),
        numericColumn("Papers", "papers"),
        numericColumn("First year", "first_year"),
        numericColumn("Last year", "last_year"),
        {title: "Years", field: "years", headerFilter: "input", formatter: "plaintext", minWidth: 260},
      ];
      const table = new Tabulator("#stats-table", {
        data: rows, columns, layout: "fitDataStretch", height: "65vh",
        placeholder: "No authors match the filters.",
      });
      table.on("dataFiltered", function (filters, filteredRows) {
        const active = filteredRows.map(row => row.getData());
        document.getElementById("author-count").textContent = active.length;
        document.getElementById("paper-count").textContent = active.reduce((sum, row) => sum + row.papers, 0);
        document.getElementById("edition-count").textContent = active.reduce((max, row) => Math.max(max, row.conferences), 0);
      });
      columns.forEach(column => {
        const label = document.createElement("label");
        label.className = "form-check-label";
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "form-check-input me-1";
        checkbox.checked = true;
        checkbox.addEventListener("change", () => {
          if (checkbox.checked) table.showColumn(column.field);
          else table.hideColumn(column.field);
        });
        label.append(checkbox, document.createTextNode(column.title));
        document.getElementById("column-toggles").append(label);
      });
      document.getElementById("clear-filters").addEventListener("click", () => table.clearHeaderFilter());
      document.getElementById("download-filtered").addEventListener("click", () => {
        table.download("csv", "weis-authors-filtered.csv", {bom: true}, "active");
      });
      document.getElementById("download-all").addEventListener("click", () => {
        table.download("csv", "weis-authors-all.csv", {bom: true}, "all");
      });
    }
  </script>
</body>
</html>
"""


def main():
    rows = build_stats(SOURCE)
    payload = json.dumps(rows, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(PAGE.replace("__STATS_DATA__", payload), encoding="utf-8")
    print(f"{len(rows)} autori -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
