## 1. Planning and source boundary setup

- [x] 1.1 Confirm the Indeed command shape and argument surface through `src/runtime_entrypoints.py`.
- [x] 1.2 Decide whether Indeed needs a dedicated extraction-spec file or can start with source-local deterministic parsing only.

## 2. Indeed source implementation

- [x] 2.1 Add a fixture-backed Indeed adapter that normalizes Indeed fixture rows into canonical `JobRecord` values.
- [x] 2.2 Add a live Indeed acquisition adapter with structured diagnostics.
- [x] 2.3 Add deterministic Indeed extraction logic for search/detail HTML.
- [x] 2.4 Add source-local filtering/query helpers needed for Indeed live acquisition.

## 3. Shared ingestion integration

- [x] 3.1 Wire Indeed into the shared ingestion flow without changing canonical persistence or evaluation behavior.
- [x] 3.2 Add the Indeed CLI/runtime command path through `src/runtime_entrypoints.py`.
- [x] 3.3 Preserve inserted-vs-updated reporting and canonical fixture/export behavior for Indeed ingestion.

## 4. Validation

- [x] 4.1 Add automated tests for Indeed fixture normalization and live-extraction helpers.
- [x] 4.2 Add CLI tests for the Indeed ingestion command path.
- [x] 4.3 Run `python3.11 -m unittest discover -s tests -v`.
- [x] 4.4 Run `env PATH=/usr/local/opt/node@20/bin:$PATH openspec validate v1-indeed-acquisition`.

## 5. Documentation

- [x] 5.1 Update `README.md` with Indeed setup and runtime commands.
- [x] 5.2 Update `CHANGELOG.md` with the Indeed acquisition feature.

## 6. Browser-backed live Indeed acquisition

- [x] 6.1 Update the change artifacts to allow Selenium-backed live Indeed scraping.
- [x] 6.2 Add Selenium as a runtime dependency for browser-backed live Indeed acquisition.
- [x] 6.3 Replace the live Indeed transport from raw HTTP to a reusable browser session.
- [x] 6.4 Add automated tests for the browser-backed diagnostics and helper behavior.
- [x] 6.5 Update `README.md` with the browser prerequisite for live Indeed scraping.
- [x] 6.6 Verify that live search-card persistence uses real href-backed `jk`
  values and canonical Indeed `viewjob` links only.
