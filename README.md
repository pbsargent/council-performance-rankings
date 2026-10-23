# Council Performance Rankings

Static GitHub Pages dashboard built from the latest `Councils Ranked.xlsx` workbook snapshot. The published data contains council-level aggregates only.

Live site: <https://pbsargent.github.io/council-performance-rankings/>

## Source workbook

Use this OneDrive workbook as the canonical source:

<https://1drv.ms/x/c/da89e4b29f338fb5/IQDfPxTsKP3iSZCztHQA9barAQgefxPyd_oJgNZIF1ZPbYA?e=8wD2Zu>

Open the link in Excel for the web and choose **File → Create a Copy → Download a Copy**. Confirm that the downloaded file is named `Councils Ranked.xlsx` and contains the expected ranking and unit-metric worksheets. Do not substitute another similarly named workbook.

## Refresh

```bash
python3 scripts/build_site.py --source "/Users/<username>/Downloads/Councils Ranked.xlsx"
python3 scripts/validate_site.py
python3 scripts/check_data_quality.py
```

Retention is copied from the workbook model without a 100% ceiling. Values above 100% are valid and must not be clamped during extraction, validation, or rendering.

Serve locally with any static web server, then open `index.html` through that server.

## Visual identity

The design follows the supplied *Scouting America Brand Guidelines (2024)*, pages 11 and 14–16. It uses the primary blue (`#003F87`), red (`#CE1126`), tan, gray, and white, with approved secondary colors and Arial typography. The signature image is unaltered artwork extracted from page 11, displayed proportionally on white with clear space of at least one fleur-de-lis height.

The site follows the system light/dark preference through `prefers-color-scheme`. Dark mode uses the guide's dark gray, dark blue, and pale blue. Red is never tinted. Signed negative values remain explicit in both themes. Branding changes do not require rebuilding the workbook payload.
