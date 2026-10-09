#!/usr/bin/env python3
"""
Genera conferences/papers/<slug>.yml: elenco semplice dei paper per la pagina principale.

Per ogni conferences/yml/<slug>.yml legge il programma e cerca i file in papers/<slug>/.
I paper senza file hanno file: null / path: null (sul sito compaiono come "non disponibile").

Formato prodotto (lo stesso che si puo' scrivere a mano, vedi _templates/papers.yml):

  name: "WEIS 2007"
  full_name: "..."
  edition: 6
  year: 2007
  location: "..."
  venue: "..."
  start_date: "2007-06-07"
  end_date: "2007-06-08"
  website: "..."
  papers:
  - id: weis2007_01
    title: '...'
    authors:
    - name: Charles Miller
      affiliation: Independent Security Evaluators
    file: weis2007_01_the-legitimate-....pdf
    path: papers/weis2007/weis2007_01_the-legitimate-....pdf

Uso:
  python3 scripts/build_papers_yml.py                 # tutte le conferenze
  python3 scripts/build_papers_yml.py weis2022        # solo alcune
"""
import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_papers import YML_DIR, collect_papers, year_from_slug  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PAPERS_DIR = ROOT / "papers"
OUT_DIR = ROOT / "conferences" / "papers"

HEADER_KEYS = ("name", "full_name", "edition", "year", "location", "venue",
               "start_date", "end_date", "website")


EXT_RANK = {".pdf": 0, ".docx": 1, ".doc": 1, ".ps": 2, ".txt": 3}


def find_file(dest_dir, prefix):
    """Miglior file <prefix>_* nella cartella: paper prima delle slide, pdf prima di doc/ps/txt."""
    hits = [p for p in dest_dir.glob(f"{prefix}_*") if p.suffix.lower() != ".yml"]
    if not hits:
        return None
    return min(hits, key=lambda p: (p.stem.endswith("-slides"), EXT_RANK.get(p.suffix.lower(), 9), p.name))


def build(yml_path):
    slug = yml_path.stem
    data = yaml.safe_load(yml_path.read_text(encoding="utf-8")) or {}
    papers = collect_papers(data)
    dest_dir = PAPERS_DIR / slug

    out = {k: data[k] for k in HEADER_KEYS if data.get(k) is not None}
    out.setdefault("year", year_from_slug(slug, data))

    entries = []
    for i, p in enumerate(papers, start=1):
        if not p["is_paper"]:
            continue
        prefix = f"{slug}_{i:02d}"
        f = find_file(dest_dir, prefix) if dest_dir.is_dir() else None
        entries.append({
            "id": prefix,
            "title": p["title"],
            "authors": p["authors_full"],
            "file": f.name if f else None,
            "path": str(f.relative_to(ROOT)) if f else None,
        })
    out["papers"] = entries

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{slug}.yml"
    out_path.write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=1000),
                        encoding="utf-8")
    n_ok = sum(1 for e in entries if e["file"])
    print(f"{slug}: {n_ok}/{len(entries)} paper con file -> {out_path.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser(description="Genera conferences/papers/<slug>.yml.")
    ap.add_argument("slugs", nargs="*", help="slug delle conferenze (es. weis2022). Default: tutte")
    args = ap.parse_args()

    if args.slugs:
        yml_files = [YML_DIR / f"{s}.yml" for s in args.slugs]
        missing = [p for p in yml_files if not p.exists()]
        if missing:
            sys.exit("yml non trovati: " + ", ".join(str(m) for m in missing))
    else:
        yml_files = sorted(YML_DIR.glob("*.yml"))

    for yml_path in yml_files:
        build(yml_path)


if __name__ == "__main__":
    main()
