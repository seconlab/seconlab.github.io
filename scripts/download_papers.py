#!/usr/bin/env python3
"""
Scarica i paper elencati in conferences/yml/*.yml e crea un indice YAML per anno.

Output:
  papers/<slug>/<slug>_NN_<titolo>.pdf   -> file scaricati (una cartella per conferenza, es. papers/weis2022/)
  papers/yml/<slug>.yml                  -> indice dei paper (anche quelli NON scaricati, con status: failed)

Strategia per ogni URL:
  1. download diretto
  2. se la pagina e' HTML, cerca dentro il primo link a .pdf/.doc/.ps/... e scarica quello
  3. fallback su Wayback Machine (CDX API): prima snapshot con mimetype application/pdf, poi qualsiasi 200
  4. se fallisce tutto -> status: failed (da scaricare a mano)

Riesecuzione: i paper che hanno gia' un file in papers/<slug>/ con prefisso <slug>_NN_ vengono saltati.
Quindi dopo aver scaricato a mano un paper basta salvarlo come papers/<slug>/<slug>_NN_qualcosa.pdf
e rilanciare lo script per aggiornare l'indice.

Uso:
  pip install pyyaml requests
  python3 scripts/download_papers.py                  # tutte le conferenze
  python3 scripts/download_papers.py weis2022 weis2009  # solo alcune
  python3 scripts/download_papers.py --force          # riscarica anche i file esistenti
  python3 scripts/download_papers.py --no-wayback     # solo download diretto
"""
import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
YML_DIR = ROOT / "conferences" / "yml"
OUT_DIR = ROOT / "papers"

TIMEOUT = 40
DELAY = 0.7  # pausa tra richieste
SESSION = requests.Session()
SESSION.headers["User-Agent"] = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

EXT_BY_TYPE = {
    "application/pdf": ".pdf",
    "application/x-pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/postscript": ".ps",
    "application/rtf": ".rtf",
    "text/plain": ".txt",
}
DOC_EXTS = {".pdf", ".doc", ".docx", ".ps", ".txt", ".ppt", ".pptx", ".rtf"}
WAYBACK_RE = re.compile(r"^https?://web\.archive\.org/web/(\d{1,14})(?:id_|im_|js_|cs_)?/(.+)$")
# I vecchi siti weisYYYY.econinfosec.org sono stati spostati sotto www.econinfosec.org/archive/weisYYYY/
WEIS_SUBDOMAIN_RE = re.compile(r"^https?://(weis\d{2,4})\.econinfosec\.org/(.*)$", re.I)


# ---------------------------------------------------------------- helpers

def log(msg):
    print(msg, flush=True)


def slugify(text, max_len=60):
    text = unquote(text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_len].rstrip("-") or "paper"


def year_from_slug(slug, data):
    if data.get("year"):
        return int(data["year"])
    m = re.search(r"(\d+)$", slug)
    if not m:
        return None
    n = int(m.group(1))
    return n if n > 100 else 2000 + n


def url_ext(url):
    path = urlparse(url).path
    ext = Path(unquote(path)).suffix.lower()
    return ext if ext in DOC_EXTS else ""


def sniff_ext(content_type, body, url):
    ct = (content_type or "").split(";")[0].strip().lower()
    if body[:5] == b"%PDF-":
        return ".pdf"
    if body[:2] == b"%!" and b"PS-Adobe" in body[:40]:
        return ".ps"
    if ct in EXT_BY_TYPE and ct != "text/plain":
        return EXT_BY_TYPE[ct]
    if url_ext(url):
        return url_ext(url)
    if ct == "text/plain":
        return ".txt"
    return ""


def is_html(content_type, body):
    ct = (content_type or "").lower()
    head = body[:600].lstrip().lower()
    return "text/html" in ct or head.startswith(b"<!doctype html") or head.startswith(b"<html") or b"<html" in head


def fetch(url):
    """Ritorna (status_code, content_type, body). Riprova una volta su 429/5xx."""
    for attempt in range(2):
        r = SESSION.get(url, timeout=TIMEOUT, allow_redirects=True, stream=True)
        if r.status_code in (429, 502, 503, 504) and attempt == 0:
            r.close()
            time.sleep(5)
            continue
        body = r.content
        return r.status_code, r.headers.get("Content-Type", ""), body, r.url
    return r.status_code, r.headers.get("Content-Type", ""), b"", url


def wayback_raw(url):
    """Trasforma un URL web.archive.org nella versione 'id_' (contenuto originale, senza toolbar)."""
    m = WAYBACK_RE.match(url)
    if not m:
        return url
    return f"https://web.archive.org/web/{m.group(1)}id_/{m.group(2)}"


def wayback_original(url):
    m = WAYBACK_RE.match(url)
    return m.group(2) if m else url


def alternate_urls(url):
    """URL originale + eventuale copia in www.econinfosec.org/archive/."""
    out = [url]
    m = WEIS_SUBDOMAIN_RE.match(wayback_original(url))
    if m:
        out.append(f"https://www.econinfosec.org/archive/{m.group(1).lower()}/{m.group(2)}")
    return out


def wayback_candidates(url, limit=4):
    """Snapshot da Wayback (CDX): prima quelli PDF, poi qualsiasi 200. Dal piu' vecchio al piu' recente."""
    original = wayback_original(url)
    out = []
    for flt in ("mimetype:application/pdf", "statuscode:200"):
        try:
            params = {
                "url": original,
                "output": "json",
                "fl": "timestamp,original,mimetype,statuscode",
                "filter": flt,
                "collapse": "digest",
                "limit": limit,
            }
            r = SESSION.get("https://web.archive.org/cdx/search/cdx", params=params, timeout=TIMEOUT)
            time.sleep(DELAY)
            if r.status_code != 200 or not r.text.strip():
                continue
            rows = r.json()[1:]
            for ts, orig, mime, status in rows:
                if str(status) not in ("200", "-"):
                    continue
                cand = f"https://web.archive.org/web/{ts}id_/{orig}"
                if cand not in out:
                    out.append(cand)
        except Exception as e:  # noqa: BLE001
            log(f"      [wayback cdx] {e}")
    return out


HREF_RE = re.compile(r"""href\s*=\s*["']([^"'#]+)["']""", re.I)


def find_doc_link(html, base_url):
    """Primo link a un documento (.pdf, .doc, ...) dentro una pagina HTML."""
    text = html.decode("utf-8", errors="ignore")
    links = [urljoin(base_url, h.strip()) for h in HREF_RE.findall(text)]
    for pref in (".pdf", ".ps", ".doc", ".docx", ".ppt", ".pptx", ".rtf", ".txt"):
        for link in links:
            if url_ext(link) == pref:
                return link
    return None


def try_document(url, use_wayback=True, depth=0):
    """
    Prova a ottenere il documento. Ritorna dict {body, ext, url, source} oppure None.
    source: direct | page_link | wayback | wayback_page_link
    """
    urls = alternate_urls(url)
    attempts = []
    for u in urls:
        if WAYBACK_RE.match(u):
            attempts.append((wayback_raw(u), "wayback"))
        else:
            attempts.append((u, "direct"))

    if use_wayback:
        for u in urls:
            for cand in wayback_candidates(u):
                if cand not in [a[0] for a in attempts]:
                    attempts.append((cand, "wayback"))

    for cand, source in attempts:
        try:
            status, ctype, body, final_url = fetch(cand)
            time.sleep(DELAY)
        except Exception as e:  # noqa: BLE001
            log(f"      [{source}] errore: {e}")
            continue
        if status != 200 or not body:
            log(f"      [{source}] HTTP {status} {cand[:110]}")
            continue
        if is_html(ctype, body):
            if depth >= 1:
                continue
            link = find_doc_link(body, final_url)
            if not link:
                log(f"      [{source}] pagina HTML senza link a documenti")
                continue
            log(f"      [{source}] pagina HTML -> provo {link[:110]}")
            res = try_document(link, use_wayback=use_wayback, depth=depth + 1)
            if res:
                res["source"] = f"{source}_page_link" if source == "wayback" else "page_link"
                return res
            continue
        ext = sniff_ext(ctype, body, final_url)
        if not ext:
            log(f"      [{source}] tipo sconosciuto ({ctype}) -> salto")
            continue
        if ext == ".txt" and len(body) < 500:
            continue
        return {"body": body, "ext": ext, "url": final_url, "source": source}
    return None


# ---------------------------------------------------------------- collezione paper

def collect_papers(data):
    """Estrae tutti i paper dal programma (qualsiasi tipo di evento con 'papers')."""
    out = []
    for day in data.get("program") or []:
        for ev in day.get("events") or []:
            for p in ev.get("papers") or []:
                if not isinstance(p, dict) or not p.get("title"):
                    continue
                authors = p.get("authors") or []
                out.append({
                    "title": p["title"].strip(),
                    "is_paper": p.get("paper", ev.get("paper", True)),
                    "url": p.get("url"),
                    "slides_url": p.get("slides"),
                    "award": p.get("award"),
                    "time": p.get("time"),
                    "date": day.get("date"),
                    "session_number": ev.get("number"),
                    "session": ev.get("title"),
                    "event_type": ev.get("type"),
                    "authors": [a["name"] if isinstance(a, dict) else str(a) for a in authors],
                    "authors_full": [a if isinstance(a, dict) else {"name": str(a)} for a in authors],
                })
    return out


def existing_file(dest_dir, prefix):
    hits = sorted(dest_dir.glob(f"{prefix}_*"))
    return hits[0] if hits else None


# ---------------------------------------------------------------- main

def process_conference(yml_path, force=False, use_wayback=True):
    slug = yml_path.stem
    data = yaml.safe_load(yml_path.read_text(encoding="utf-8")) or {}
    year = year_from_slug(slug, data)
    papers = collect_papers(data)
    if not papers:
        log(f"== {slug}: nessun paper nel programma, salto")
        return None

    dest_dir = OUT_DIR / slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    log(f"== {slug} ({year}): {len(papers)} paper -> {dest_dir.relative_to(ROOT)}")

    entries = []
    n_ok = n_fail = n_skip = 0
    for i, p in enumerate(papers, start=1):
        prefix = f"{slug}_{i:02d}"
        entry = {
            "id": prefix,
            "conference": slug,
            "year": year,
            "title": p["title"],
            "authors": p["authors"],
            "authors_full": p["authors_full"],
            "session_number": p["session_number"],
            "session": p["session"],
            "event_type": p["event_type"],
            "date": p["date"],
            "time": p["time"],
            "award": p["award"],
            "url": p["url"],
            "slides_url": p["slides_url"],
            "file": None,
            "path": None,
            "status": None,
            "source": None,
            "downloaded_url": None,
            "error": None,
        }
        log(f"  [{i:02d}/{len(papers)}] {p['title'][:90]}")

        already = existing_file(dest_dir, prefix)
        if already and not force:
            entry.update(file=already.name, path=str(already.relative_to(ROOT)), status="downloaded",
                         source="existing")
            n_skip += 1
            log(f"      gia' presente: {already.name}")
            entries.append(entry)
            continue

        if not p["url"]:
            entry.update(status="no_url", error="nessun url nel yml")
            n_fail += 1
            log("      nessun url")
            entries.append(entry)
            continue

        res = try_document(p["url"], use_wayback=use_wayback)
        if not res:
            entry.update(status="failed", error="download fallito (diretto + wayback)")
            n_fail += 1
            log("      FALLITO")
            entries.append(entry)
            continue

        if already and force:
            already.unlink()
        fname = f"{prefix}_{slugify(p['title'])}{res['ext']}"
        fpath = dest_dir / fname
        fpath.write_bytes(res["body"])
        entry.update(file=fname, path=str(fpath.relative_to(ROOT)), status="downloaded",
                     source=res["source"], downloaded_url=res["url"])
        n_ok += 1
        log(f"      OK [{res['source']}] {fname} ({len(res['body']) // 1024} KB)")
        entries.append(entry)

    index = {
        "conference": slug,
        "name": data.get("name"),
        "year": year,
        "papers_dir": str(dest_dir.relative_to(ROOT)),
        "total": len(entries),
        "downloaded": n_ok + n_skip,
        "failed": n_fail,
        "papers": entries,
    }
    yml_out_dir = OUT_DIR / "yml"
    yml_out_dir.mkdir(parents=True, exist_ok=True)
    out_path = yml_out_dir / f"{slug}.yml"
    out_path.write_text(
        yaml.safe_dump(index, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    log(f"   -> indice: {out_path.relative_to(ROOT)}  (ok {n_ok}, esistenti {n_skip}, falliti {n_fail})\n")
    return index


def main():
    ap = argparse.ArgumentParser(description="Scarica i paper WEIS dai yml delle conferenze.")
    ap.add_argument("slugs", nargs="*", help="slug delle conferenze (es. weis2022). Default: tutte")
    ap.add_argument("--force", action="store_true", help="riscarica anche i file gia' presenti")
    ap.add_argument("--no-wayback", action="store_true", help="non usare la Wayback Machine")
    ap.add_argument("--out", default=None, help="cartella di output (default: papers/)")
    args = ap.parse_args()

    global OUT_DIR
    if args.out:
        OUT_DIR = Path(args.out).resolve()

    if args.slugs:
        yml_files = [YML_DIR / f"{s}.yml" for s in args.slugs]
        missing = [p for p in yml_files if not p.exists()]
        if missing:
            sys.exit("yml non trovati: " + ", ".join(str(m) for m in missing))
    else:
        yml_files = sorted(YML_DIR.glob("*.yml"))

    failed = []
    for yml_path in yml_files:
        idx = process_conference(yml_path, force=args.force, use_wayback=not args.no_wayback)
        if idx:
            failed += [e for e in idx["papers"] if e["status"] != "downloaded"]

    log("=" * 70)
    if failed:
        log(f"DA SCARICARE A MANO ({len(failed)}):")
        for e in failed:
            log(f"  {e['id']}  {e['title'][:80]}")
            log(f"      {e['url'] or '(nessun url)'}")
        log("\nSalva il file come papers/<slug>/<id>_<nome>.pdf e rilancia lo script per aggiornare l'indice.")
    else:
        log("Tutti i paper scaricati.")


if __name__ == "__main__":
    main()

# Per la pagina principale (conferences/papers/<slug>.yml) vedi scripts/build_papers_yml.py
