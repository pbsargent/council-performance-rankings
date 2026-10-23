# Council Performance Rankings

Static GitHub Pages dashboard built from the latest `Councils Ranked.xlsx` workbook snapshot. The published data contains council-level aggregates only.

Live site: <https://pbsargent.github.io/council-performance-rankings/>

## Source workbook

Use this OneDrive workbook as the canonical source:

<https://1drv.ms/x/c/da89e4b29f338fb5/IQDfPxTsKP3iSZCztHQA9barAQgefxPyd_oJgNZIF1ZPbYA?e=8wD2Zu>

Open the link in Excel for the web and choose **File → Create a Copy → Download a Copy**. Confirm that the downloaded file is named `Councils Ranked.xlsx` and contains the expected ranking and unit-metric worksheets. Do not substitute another similarly named workbook.

## Daily refresh (hardened workflow)

The active daily automation runs at 8:00 AM America/Chicago. It downloads the canonical source, runs the gates below, publishes only a passing candidate, verifies the exact pushed commit on Pages, and emails the owner on success or failure. The notification recipient and connected Gmail account are saved in the private automation configuration, not in the published site.

1. Read this README. Confirm `main` has no tracked/staged changes, fetch `origin/main`, and confirm local HEAD equals origin/main. Do not reset or include other work. Preserve unrelated untracked files. Check the previous automation result for an unresolved push/deployment failure; resolve that state before creating another refresh.
2. Capture an acquisition-start timestamp **before** opening the canonical link and requesting its download. Use the original new browser download as `--source`; browser suffixes such as `Councils Ranked (7).xlsx` are accepted. Never rename, touch, or copy an old file to make it appear fresh. Confirm the source workbook title in Excel for the web is `Councils Ranked.xlsx`. Direct HTTP download may fail; use File → Create a Copy → Download a Copy. If no fresh file arrives, stop and send a failure email.
3. Run the guarded preparation command. A new private run directory retains the source snapshot, candidate, source SHA-256, original acquisition time, population differences, retention maximum/count above 100%, TAY coverage, and gate results. No third-party Python packages are required.

```bash
python3 scripts/prepare_refresh.py \
  --source "/absolute/path/to/original/new/Councils Ranked (7).xlsx" \
  --acquisition-started-at "<timezone-qualified ISO timestamp captured before download>" \
  --run-dir "/private/tmp/<unique-refresh-run>/run"
python3 scripts/validate_site.py
python3 scripts/check_data_quality.py
python3 -m unittest discover -s scripts -p 'test_*.py'
node --check assets/dashboard.js
```

The run directory must not already exist. Add `--check-only` for a diagnostic build that does not replace the working payload. `prepare_refresh.py` checks original file freshness within a one-hour acquisition window, required sheets and fixed-column headers, council population and joins, exact source TAY and retention values, aggregate-only schema, competition ranks (including ties), the dynamic peer rule, national totals, brand artwork, and system-theme support. Only after all gates pass does it atomically replace working `data/latest.json`. A failed gate leaves that file intact. The source workbook's internal reporting date is distinct from its download time; downloading does not prove that upstream source data has changed.

Retention is copied from the workbook model without a 100% ceiling. Values above 100% are valid and must never be clamped, rejected, or rewritten. Existing source retention blanks remain blank; newly lost retention/TAY values stop the guarded refresh. Existing source TAY blanks and the membership/unit-metric population difference remain disclosed caveats. Any new range, bucket-reconciliation, duplicate-row, join, schema, privacy, or site-validation failure blocks publication. Do not weaken a check just to publish.

4. Review the run report and `git diff --check`. Council count and peer count are source-derived: 223 councils and 9 Capitol Area peers were validated on October 22, 2026; these are observations, not fixed assertions. Disclose added/removed council identifiers from the report. Do not assume the historical 227-council population or 12-peer count.
5. For routine data refreshes, the only tracked change allowed is `data/latest.json`. Stage that exact file (never `git add .`), review the staged diff, commit on `main` with a dated refresh message, and push `origin/main`. Preserve all HTML/CSS/JS, signature artwork, and source/validation scripts. If any additional tracked files change, stop and report them. Load the GitHub credential from the configured private file without printing it. If a push fails, retain the local commit and report its SHA; do not accumulate new refresh commits on top of an unresolved failed push.
6. Verify the **pushed commit**, never an older successful deployment:

```bash
python3 scripts/verify_release.py \
  --commit "<full pushed commit SHA>" \
  --expected "/private/tmp/<unique-refresh-run>/run/latest.json" \
  --report "/private/tmp/<unique-refresh-run>/run/deployment.json"
```

This waits for Pages success for that SHA, then requires HTTP 200 and exact committed bytes for all four pages, CSS, JavaScript, signature, and JSON with cache-busting queries. JSON equality also verifies timestamp, source population, TAY, uncapped retention, and the aggregate-only payload. Keep private run artifacts and workbooks out of git and the public site.

7. Send exactly one outcome email per run to the recipient saved in the automation, including source acquisition time, council count and population changes, TAY coverage/caveats, maximum retention and number above 100%, commit SHA, Pages/live verification result, and live URL. On failure, state the stage, concise cause, any local unpushed commit, and the last verified public state; do not claim success. A post-push failure may already have changed the public site: report that accurately and do not automatically roll back or force-push. Send failure email even when source acquisition fails before a report exists. If email delivery fails, surface that separately in the automation result; do not report it as sent.

### Lower-level diagnostic build

`python3 scripts/build_site.py --source "Councils Ranked.xlsx" --output "/private/tmp/candidate.json"` remains available for diagnostics. It checks workbook identity and worksheet headers, but does not establish a fresh acquisition window or authorize publication. Use the guarded workflow for daily refreshes.

Serve locally with any static web server, then open `index.html` through that server.

## Visual identity

The design follows the supplied *Scouting America Brand Guidelines (2024)*, pages 11 and 14–16. It uses the primary blue (`#003F87`), red (`#CE1126`), tan, gray, and white, with approved secondary colors and Arial typography. The signature image is unaltered artwork extracted from page 11, displayed proportionally on white with clear space of at least one fleur-de-lis height.

The site follows the system light/dark preference through `prefers-color-scheme`. Dark mode uses the guide's dark gray, dark blue, and pale blue. Red is never tinted. Signed negative values remain explicit in both themes. Branding changes do not require rebuilding the workbook payload.
