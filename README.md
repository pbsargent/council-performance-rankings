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
python3 scripts/check_data_quality.py --source "/private/tmp/<unique-refresh-run>/run/Councils Ranked.xlsx"
python3 -m unittest discover -s scripts -p 'test_*.py'
node --check assets/dashboard.js
node --test scripts/test_cst.js
```

The run directory must not already exist. Add `--check-only` for a diagnostic build that does not replace the working payload. `prepare_refresh.py` checks original file freshness within a one-hour acquisition window, required sheets and fixed-column headers, council population and joins, exact source TAY and retention values, aggregate-only schema, competition ranks (including ties), the dynamic peer rule, national totals, brand artwork, and system-theme support. Only after all gates pass does it atomically replace working `data/latest.json`. A failed gate leaves that file intact. The source workbook's internal reporting date is distinct from its download time; downloading does not prove that upstream source data has changed.

The imported Unit Metrics field named “retention” is copied from the workbook model without a 100% ceiling. Its cohort and measurement window are unverified; do not interpret it as a verified annual cohort-retention measure. Values above 100% and zero values are valid and must never be clamped, rejected, or rewritten. Zero unit counts are valid as programs open or close. Existing source metric blanks remain blank; a newly blank imported “retention” value is also allowed when that council/program has exactly zero source units, and is disclosed in the private report as `zero_unit_metric_blanks`. Blank does not become a numeric zero. Newly lost values for programs with positive or unknown unit counts, and newly lost TAY values, still stop the guarded refresh. Existing source TAY blanks and the membership/unit-metric population difference remain disclosed caveats. Any new range, bucket-reconciliation, duplicate-row, join, schema, privacy, or site-validation failure blocks publication. Do not weaken a check just to publish.

4. Review the run report and `git diff --check`. Council count and peer count are source-derived: 223 councils and 9 Capitol Area peers were validated on October 22, 2026; these are observations, not fixed assertions. Disclose added/removed council identifiers from the report. Do not assume the historical 227-council population or 12-peer count.

   Before reporting any missing council, search the web using its name and number for a merger, renaming, closure, or other explanation. Prefer official council or Scouting America announcements. Retain the supporting URLs, announcement dates, any explicitly stated effective date, and successor council identifiers in private run evidence; include the explanation and source link in the outcome email. If no reliable explanation is found, report the absence as unresolved and state that the search was inconclusive. An announcement date is not necessarily the effective date, and a merger announcement alone does not prove how the workbook incorporates it. Keep source-derived values and all validation gates unchanged; do not combine figures or replace workbook data based on web research. Apply this check to missing-council failure notifications as well as successful refreshes.

   Known context: Quivira Council's [October 28, 2026 announcement](https://quivira.org/welcome-coronado-council/) confirms Coronado Council's merger into Quivira. Use this context when explaining the absence of Coronado Area #192 and the successor Quivira #198, while validating the workbook independently.
5. For routine data refreshes, the only tracked change allowed is `data/latest.json`. Stage that exact file (never `git add .`), review the staged diff, commit on `main` with a dated refresh message, and push `origin/main`. Preserve all HTML/CSS/JS, signature artwork, and source/validation scripts. If any additional tracked files change, stop and report them. Load the GitHub credential from the configured private file without printing it. If a push fails, retain the local commit and report its SHA; do not accumulate new refresh commits on top of an unresolved failed push.
6. Verify the **pushed commit**, never an older successful deployment:

```bash
python3 scripts/verify_release.py \
  --commit "<full pushed commit SHA>" \
  --expected "/private/tmp/<unique-refresh-run>/run/latest.json" \
  --report "/private/tmp/<unique-refresh-run>/run/deployment.json"
```

This waits for Pages success for that SHA, then requires HTTP 200 and exact committed bytes for all site pages, CSS, JavaScript, signature, and JSON with cache-busting queries. JSON equality also verifies timestamp, source population, TAY, uncapped retention, and the aggregate-only payload. Keep private run artifacts and workbooks out of git and the public site.

7. Send exactly one outcome email per run to the recipient saved in the automation, including source acquisition time, council count and population changes, TAY coverage/caveats, maximum retention and number above 100%, commit SHA, Pages/live verification result, and live URL. On failure, state the stage, concise cause, any local unpushed commit, and the last verified public state; do not claim success. A post-push failure may already have changed the public site: report that accurately and do not automatically roll back or force-push. Send failure email even when source acquisition fails before a report exists. If email delivery fails, surface that separately in the automation result; do not report it as sent.

   In the success email, use `report.json` from the current run. Report the ranking and Unit Metrics unit totals, the separate club and Coming exclusions, any overlap counted once, and the remaining unit gap and number of affected councils, including zero. The gap is the expected Unit Metrics count after exclusions minus the reported Unit Metrics count. Council gaps remain visible in the private data-quality report even when they cancel nationally. Label `youth_counts.primary_youth` as **Primary Youth (Rankings)** and `youth_counts.total_youth` as **Total Youth (Unit Metrics)**. These are different source measures.

### Lower-level diagnostic build

`python3 scripts/build_site.py --source "Councils Ranked.xlsx" --output "/private/tmp/candidate.json"` remains available for diagnostics. It checks workbook identity and worksheet headers, but does not establish a fresh acquisition window or authorize publication. Use the guarded workflow for daily refreshes.

Serve locally with any static web server, then open `index.html` through that server.

## Chartered and Coming units

The Councils unit total includes both chartered and Coming units and remains the count used for peer matching. The build reads the hidden Units worksheet, where `Coming` is `Yes` for Coming units and blank for chartered units. It rejects unknown flags, missing or duplicate unit IDs, unmatched councils, and per-council totals that do not reconcile to the Councils worksheet. Only the Coming count per council and its national sum are published; the chartered count is the combined total minus Coming. Overview and CST show the split, and Rankings keeps the combined total. Unit Health, BeAScout and the separate geography snapshot keep their own source populations.

## Geographic context

The council overview and rankings include `square_miles` (matched ZIP land area) and `urban_pct` (2020 Census urban population share), imported unchanged from Councils columns R and S. The source header in R is spelled “Sqare Miles”; Data_Census_Gov supplies the full definitions. Source blanks remain unavailable. These fields do not change peer selection or growth ranks. The guarded refresh checks both source headers and exact values.

The Overview's **Unit locations and population** panel compares the share of matched units and residents in majority-rural ZIP areas. It lists the 2020 Census rural resident share separately because that measure classifies rural areas within ZIP areas. The national context counts councils with at least 90% of reported units classified within their matched ZIP areas. **Unit Health** lists all programs for the selected council, using classified pins as the share denominator and reporting coverage against all pins. Exploring includes posts and clubs.

`data/unit-geography.json` is a separate dated National Pin Data Report and 2020 Census snapshot. The daily rankings workbook refresh does not update it. For a reviewed replacement, run `python3 scripts/unit_geography.py --comparison /path/to/private/comparison.json --report-date YYYY-MM-DD`, then run the normal site validators. Only the generated council and program aggregates belong in the public site.

## CST Dashboard

`cst.html` groups councils by the snapshot's `cst` assignment, with an All CSTs view and source-derived territory links (`cst.html?cst=7`, for example). Council counts and CST lists are never fixed. Unknown CST links show All CSTs with an explanatory notice; missing source assignments appear in an Unassigned CST group.

Territory membership totals sum the councils in view. YOY and year-end growth divide the summed youth change by the corresponding summed baseline, rather than averaging council rates. TAY penetration uses only councils with positive TAY, including those same councils in its youth numerator. Missing TAY remains unavailable and affected councils are named. An empty selection has undefined membership totals and rates, rather than fabricated zeros.

Search narrows summaries, growth comparisons, source coverage, and council details together; reset restores the selected territory. Council rows expand to membership, market/geographic context, program Unit Metrics, and BeAScout indicators, with links to the council Overview and Unit Health. Program/PIN populations remain separate from membership totals; council ranks remain national. Imported “retention” values remain uncapped and disclose their unverified cohort/window. `node --test scripts/test_cst.js` covers partitioning, national reconciliation, count-weighted growth, TAY coverage, empty/zero-denominator cases, source changes, search scope, and imported metric preservation.

**Print council report** at the bottom of an expanded council opens a print preview with Council Details and a peer comparison. Use **Print / Save as PDF** for the two-page Letter layout. The preview reads the published workbook snapshot and the separately dated unit geography snapshot. It reports peer medians and identifies geography coverage where available.

## Visual identity

The design follows the supplied *Scouting America Brand Guidelines (2024)*, pages 11 and 14–16. It uses the primary blue (`#003F87`), red (`#CE1126`), tan, gray, and white, with approved secondary colors and Arial typography. The signature image is unaltered artwork extracted from page 11, displayed proportionally on white with clear space of at least one fleur-de-lis height.

The site follows the system light/dark preference through `prefers-color-scheme`. Dark mode uses the guide's dark gray, dark blue, and pale blue. Red is never tinted. Signed negative values remain explicit in both themes. Branding changes do not require rebuilding the workbook payload.
