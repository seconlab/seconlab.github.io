# secon.github.io

To test:
run in local:

## Author statistics

`/stats` serves the static author ranking. Regenerate it after updating
`conferences/papers/*.yml`:

```sh
python3 scripts/update_stats.py
```

Requires `pandas` and `pyyaml`. The script writes `stats/index.html`; no backend
is needed. Rankings count distinct conference editions with at least one paper,
then paper credits (including unavailable files), not physical attendance.
Names are matched ignoring case and repeated whitespace, without merging spelling
variants. Filters update the summary cards; CSV export supports all or filtered rows.