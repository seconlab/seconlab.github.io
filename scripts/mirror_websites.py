#!/usr/bin/env python3
"""
Scarica una copia completa (mirror) dei siti web delle conferenze in websites/<slug>/,
mantenendo la struttura originale (pagine, css, immagini, pdf...).

Per ogni conferences/yml/<slug>.yml:
  1. prende la home da archive_urls.home / archive_urls.wayback_home / source_urls.home / website
  2. se il sito e' ancora online        -> mirror con wget
  3. se e' un URL web.archive.org o il sito e' morto -> wayback_machine_downloader (gem Ruby)

Requisiti:
  brew install wget
  gem install wayback_machine_downloader_straw   (fork mantenuto, con retry; con Ruby >= 3:
                                                  export PATH="/opt/homebrew/opt/ruby/bin:$PATH")

Uso:
  python3 scripts/mirror_websites.py                 # tutte le conferenze
  python3 scripts/mirror_websites.py weis2022        # solo alcune
  python3 scripts/mirror_websites.py --dry-run       # mostra solo cosa farebbe
  python3 scripts/mirror_websites.py --force         # riscarica anche se websites/<slug>/ esiste gia'
  python3 scripts/mirror_websites.py --check         # elenca i file mancanti (immagini, pdf...) nelle copie esistenti

Nota: le copie da Wayback possono essere incomplete (file mai archiviati, pagine dinamiche vuote).
Rilanciare con --force su una copia Wayback scarica solo i file mancanti (quelli presenti vengono saltati).
"""
import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_papers import SESSION, WAYBACK_RE, YML_DIR  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "websites"
# registro dei siti scaricati (slug -> url, source live|wayback): letto da index.html come site.data.websites
REGISTRY = ROOT / "conferences" / "websites.yml"
TIMEOUT = 30


def log(msg):
    print(msg, flush=True)


def home_url(data):
    for group in ("archive_urls", "source_urls"):
        urls = data.get(group) or {}
        for key in ("home", "wayback_home"):
            if urls.get(key):
                return urls[key]
    return data.get("website")


def is_live(url):
    """True se il sito risponde 200 restando sullo stesso host (niente redirect verso archivi)."""
    try:
        r = SESSION.get(url, timeout=TIMEOUT, allow_redirects=True)
    except Exception as e:  # noqa: BLE001
        log(f"   offline: {e.__class__.__name__}")
        return False
    same_host = urlparse(r.url).netloc.lower() == urlparse(url).netloc.lower()
    if r.status_code != 200 or not same_host:
        log(f"   offline: HTTP {r.status_code} -> {r.url[:100]}")
    return r.status_code == 200 and same_host


def wget_cmd(url, dest):
    """Mirror di un sito vivo; --cut-dirs toglie il prefisso di path (es. /archive/weis2006/)."""
    path = urlparse(url).path
    dir_path = path if path.endswith("/") else path.rsplit("/", 1)[0] + "/"
    cut = len([p for p in dir_path.split("/") if p])
    return [
        "wget", "--mirror", "--page-requisites", "--convert-links", "--adjust-extension",
        "--no-parent", "--no-host-directories", f"--cut-dirs={cut}",
        "--wait=1", "--random-wait", "--tries=3", "--timeout=30",
        # "?" nei nomi file diventa "@": altrimenti il server lo legge come query string e la pagina non si apre
        "--restrict-file-names=windows",
        # rumore tipico dei siti WordPress (feed, api, commenti), inutile in un archivio statico
        "--reject-regex", r"(wp-json|xmlrpc\.php|/feed/?$|/comments/|\?(replytocom|share|s)=|wp-login)",
        "-e", "robots=off", "--user-agent=Mozilla/5.0",
        "-P", str(dest), url,
    ]


def find_wayback_tool():
    """Eseguibile del gem: su PATH oppure nella bin dir dei gem Homebrew (non sempre in PATH)."""
    found = shutil.which("wayback_machine_downloader")
    if found:
        return found
    hits = sorted(Path("/opt/homebrew/lib/ruby/gems").glob("*/bin/wayback_machine_downloader"))
    return str(hits[-1]) if hits else None


def wayback_cmd(url, dest, year=None):
    """Scarica da Wayback l'intero sito originale.

    Limite temporale: fine dell'anno della conferenza + 3. Non si usa il timestamp del singolo snapshot
    perche' immagini e pdf spesso sono stati archiviati anni dopo le pagine html.
    """
    m = WAYBACK_RE.match(url)
    original = m.group(2) if m else url
    # il tool scarica tutto cio' che inizia con l'URL dato: serve la cartella, non index.htm
    original = original if original.endswith("/") else original.rsplit("/", 1)[0] + "/"
    cmd = [find_wayback_tool(), original, "-d", str(dest), "-c", "3"]
    if year:
        cmd += ["--to", f"{int(year) + 3}1231"]
    return cmd


SRC_RE = re.compile(r"""(?:src|href)\s*=\s*["']([^"'#?]+)""", re.I)


def missing_assets(dest):
    """Riferimenti locali (immagini, css, pdf...) citati nelle pagine html ma assenti su disco."""
    missing = set()
    for page in dest.rglob("*.htm*"):
        text = page.read_text(encoding="utf-8", errors="ignore")
        # i listing automatici di Apache ("Index of /papers") citano icone e file mai archiviati: rumore
        if re.search(r"<title>\s*Index of /", text, re.I):
            continue
        for ref in SRC_RE.findall(text):
            ref = unquote(ref.strip())
            if not ref or "://" in ref or ref.startswith(("mailto:", "javascript:", "data:", "//")):
                continue
            target = (dest if ref.startswith("/") else page.parent) / ref.lstrip("/")
            if not target.exists() and not (target.parent / (target.name + ".html")).exists():
                missing.add(str(target.relative_to(dest)) if target.is_relative_to(dest) else ref)
    return sorted(missing)


def run(cmd, dry_run, retries=1):
    """Esegue il comando; con retries>1 riprova dopo una pausa (Wayback risponde spesso 503)."""
    log("   $ " + " ".join(cmd))
    if dry_run:
        return 0
    for attempt in range(1, retries + 1):
        code = subprocess.call(cmd)
        if code == 0 or attempt == retries:
            return code
        wait = 30 * attempt
        log(f"   exit={code}, riprovo tra {wait}s ({attempt}/{retries})")
        time.sleep(wait)
    return code


def mirror(yml_path, force=False, dry_run=False):
    slug = yml_path.stem
    data = yaml.safe_load(yml_path.read_text(encoding="utf-8")) or {}
    url = home_url(data)
    dest = OUT_DIR / slug
    log(f"== {slug}: {url}")
    if not url:
        log("   nessun url, salto")
        return "no_url"
    if dest.exists() and any(dest.iterdir()) and not force:
        log(f"   gia' presente: {dest.relative_to(ROOT)} (usa --force per riscaricare)")
        return "existing"

    if WAYBACK_RE.match(url) or not is_live(url):
        if not find_wayback_tool():
            log("   wayback_machine_downloader non installato: gem install wayback_machine_downloader_straw")
            return "missing_tool"
        cmd, source, retries = wayback_cmd(url, dest, data.get("year")), "wayback", 4
    else:
        if not shutil.which("wget"):
            log("   wget non installato: brew install wget")
            return "missing_tool"
        cmd, source, retries = wget_cmd(url, dest), "live", 1

    if not dry_run:
        dest.mkdir(parents=True, exist_ok=True)
    code = run(cmd, dry_run, retries)
    # wget ritorna 8 anche per singoli 404 dentro un mirror altrimenti riuscito
    ok = code in (0, 8) if source == "live" else code == 0
    log(f"   {'OK' if ok else 'ERRORE'} [{source}] exit={code}")
    if ok and not dry_run:
        update_registry(slug, url, source)
        miss = missing_assets(dest)
        if miss:
            log(f"   file mancanti ({len(miss)}): " + ", ".join(miss[:8]) + (" ..." if len(miss) > 8 else ""))
    log("")
    return source if ok else "failed"


def update_registry(slug, url, source):
    reg = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.exists() else {}
    reg = reg or {}
    reg[slug] = {"url": url, "source": source, "mirrored": time.strftime("%Y-%m-%d")}
    REGISTRY.write_text(yaml.safe_dump(dict(sorted(reg.items())), allow_unicode=True, sort_keys=False),
                        encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Mirror dei siti web delle conferenze in websites/<slug>/.")
    ap.add_argument("slugs", nargs="*", help="slug delle conferenze (es. weis2022). Default: tutte")
    ap.add_argument("--force", action="store_true", help="riscarica anche se la cartella esiste")
    ap.add_argument("--dry-run", action="store_true", help="mostra i comandi senza eseguirli")
    ap.add_argument("--check", action="store_true", help="non scarica: elenca solo i file mancanti nelle copie esistenti")
    args = ap.parse_args()

    if args.slugs:
        yml_files = [YML_DIR / f"{s}.yml" for s in args.slugs]
        missing = [p for p in yml_files if not p.exists()]
        if missing:
            sys.exit("yml non trovati: " + ", ".join(str(m) for m in missing))
    else:
        yml_files = sorted(YML_DIR.glob("*.yml"))

    if args.check:
        for yml_path in yml_files:
            dest = OUT_DIR / yml_path.stem
            if not dest.is_dir():
                continue
            miss = missing_assets(dest)
            log(f"== {yml_path.stem}: {len(miss)} file mancanti")
            for m in miss:
                log(f"   {m}")
        return

    results = {}
    for yml_path in yml_files:
        results[yml_path.stem] = mirror(yml_path, force=args.force, dry_run=args.dry_run)

    log("=" * 70)
    for slug, res in results.items():
        log(f"  {slug:12s} {res}")


if __name__ == "__main__":
    main()
