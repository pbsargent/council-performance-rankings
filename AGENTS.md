# Council Rankings maintenance

Read README.md completely before refresh or publication work. Use its guarded daily refresh workflow and preserve its source, privacy, retention, and design contracts.

- The canonical source is the exact OneDrive link documented in README.md. No workbook substitutes or stale-download fallback. Record acquisition start before downloading; pass the original new browser download to scripts/prepare_refresh.py.
- Routine scheduled runs may change and stage only data/latest.json. Preserve unrelated files. Never reset user work, include unrelated commits, or weaken validation to obtain a passing refresh.
- Derive council population and peers from the validated source. Do not fix counts at 227 councils or 12 peers. Preserve TAY blanks and disclose caveats. All retention values, including those above 100%, must remain identical to the workbook.
- Publish council aggregates only. Source workbooks, private run reports, credentials, and unit-level rows must never be committed or deployed.
- Preserve the Scouting America signature, palette, Arial typography, responsive layout, and system light/dark support. Branding changes require explicit design work and visual verification; a daily source refresh does not authorize redesign.
- Run the required validators and regression tests before committing. Push only the reviewed refresh commit. Run scripts/verify_release.py against that exact commit and retained candidate.
- Follow the private automation's email instructions on every success or failure, including acquisition failures. Never expose credentials or claim an email was sent without a successful send result.
