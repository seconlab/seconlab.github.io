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

Nota: le copie da Wayback possono essere incomplete (file mai archiviati, pagine dinamiche vuote).
"""
import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

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


def wayback_cmd(url, dest):
    """Scarica da Wayback l'intero sito originale, fino allo snapshot indicato nell'URL (se presente)."""
    m = WAYBACK_RE.match(url)
    original = m.group(2) if m else url
    # il tool scarica tutto cio' che inizia con l'URL dato: serve la cartella, non index.htm
    original = original if original.endswith("/") else original.rsplit("/", 1)[0] + "/"
    cmd = [find_wayback_tool(), original, "-d", str(dest), "-c", "3"]
    if m:
        cmd += ["--to", m.group(1)]
    return cmd


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
        cmd, source, retries = wayback_cmd(url, dest), "wayback", 4
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
    log(f"   {'OK' if ok else 'ERRORE'} [{source}] exit={code}\n")
    if ok and not dry_run:
        update_registry(slug, url, source)
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
    args = ap.parse_args()

    if args.slugs:
        yml_files = [YML_DIR / f"{s}.yml" for s in args.slugs]
        missing = [p for p in yml_files if not p.exists()]
        if missing:
            sys.exit("yml non trovati: " + ", ".join(str(m) for m in missing))
    else:
        yml_files = sorted(YML_DIR.glob("*.yml"))

    results = {}
    for yml_path in yml_files:
        results[yml_path.stem] = mirror(yml_path, force=args.force, dry_run=args.dry_run)

    log("=" * 70)
    for slug, res in results.items():
        log(f"  {slug:12s} {res}")


if __name__ == "__main__":
    main()
