# Council Performance Rankings

Static GitHub Pages dashboard built from the latest `Councils Ranked.xlsx` workbook snapshot. The published data contains council-level aggregates only.

Live site: <https://pbsargent.github.io/council-performance-rankings/>

## Refresh

```bash
python3 scripts/build_site.py --source "/path/to/Councils Ranked.xlsx"
python3 scripts/validate_site.py
python3 scripts/check_data_quality.py
```

Serve locally with any static web server, then open `index.html` through that server.
