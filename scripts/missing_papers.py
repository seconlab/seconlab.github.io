#!/usr/bin/env python3
"""
Elenca i paper da scaricare a mano, con cartella e nome file da usare.

Legge papers/yml/*.yml (generati da download_papers.py) e controlla anche il disco,
quindi un paper gia' salvato a mano non compare piu'.

Uso:
  python3 scripts/missing_papers.py                 # tutte le conferenze
  python3 scripts/missing_papers.py weis2010        # solo alcune
  python3 scripts/missing_papers.py --csv out.csv   # esporta anche in CSV
  python3 scripts/missing_papers.py --mkdir         # crea le cartelle mancanti

Dopo aver salvato i file rilancia download_papers.py per aggiornare gli indici yml.
"""
import argparse
import csv
import sys
from pathlib import Path
from urllib.parse import quote_plus

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_papers import slugify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PAPERS_DIR = ROOT / "papers"
INDEX_DIR = PAPERS_DIR / "yml"


def main():
    ap = argparse.ArgumentParser(description="Paper da scaricare manualmente.")
    ap.add_argument("slugs", nargs="*", help="slug delle conferenze (es. weis2010). Default: tutte")
    ap.add_argument("--csv", help="salva l'elenco anche in un file CSV")
    ap.add_argument("--mkdir", action="store_true", help="crea le cartelle di destinazione mancanti")
    args = ap.parse_args()

    if args.slugs:
        index_files = [INDEX_DIR / f"{s}.yml" for s in args.slugs]
    else:
        index_files = sorted(INDEX_DIR.glob("*.yml"))
    if not index_files or not all(p.exists() for p in index_files):
        sys.exit(f"Indici non trovati in {INDEX_DIR}. Esegui prima scripts/download_papers.py")

    rows = []
    for idx_path in index_files:
        index = yaml.safe_load(idx_path.read_text(encoding="utf-8")) or {}
        slug = index.get("conference", idx_path.stem)
        dest_dir = PAPERS_DIR / slug
        for p in index.get("papers") or []:
            if any(dest_dir.glob(f"{p['id']}_*")):
                continue
            filename = f"{p['id']}_{slugify(p['title'])}.pdf"
            query = f"\"{p['title']}\" {' '.join(p.get('authors') or [])}"
            rows.append({
                "conference": slug,
                "year": p.get("year"),
                "id": p["id"],
                "title": p["title"],
                "authors": ", ".join(p.get("authors") or []),
                "status": p.get("status"),
                "url": p.get("url") or "",
                "scholar": "https://scholar.google.com/scholar?q=" + quote_plus(query),
                "folder": str(dest_dir.relative_to(ROOT)),
                "filename": filename,
                "path": str((dest_dir / filename).relative_to(ROOT)),
            })
            if args.mkdir:
                dest_dir.mkdir(parents=True, exist_ok=True)

    if not rows:
        print("Nessun paper da scaricare a mano.")
        return

    current = None
    for r in rows:
        if r["conference"] != current:
            current = r["conference"]
            n = sum(1 for x in rows if x["conference"] == current)
            print(f"\n=== {current} ({n} da scaricare) -> cartella: {r['folder']}/")
        print(f"\n  [{r['id']}] {r['title']}")
        if r["authors"]:
            print(f"    autori:  {r['authors']}")
        print(f"    stato:   {r['status']}")
        print(f"    url:     {r['url'] or '(nessun url nel yml)'}")
        print(f"    cerca:   {r['scholar']}")
        print(f"    salva:   {r['path']}")

    print(f"\nTotale da scaricare a mano: {len(rows)}")
    print("Il nome deve iniziare con '<id>_' (l'estensione puo' essere .pdf, .doc, ...).")
    print("Poi rilancia: python3 scripts/download_papers.py")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"CSV salvato in {args.csv}")


if __name__ == "__main__":
    main()
