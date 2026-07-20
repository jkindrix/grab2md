# Contributing to html2md

html2md is an alpha-stage, CLI-first project. Contributions should preserve its
local-first operation, honest request identity, explicit failure contracts,
sequential crawl policy, and guarded outbound-network boundary. New cloud
services, login flows, concurrency, site-specific cleanup rules, or stable
library APIs require an evidence-backed design decision before implementation.

## Set up a development checkout

Requirements are Python 3.11 or newer, Poetry 1.8.3, and Node.js for extension
tests. Chromium is required only for the runtime extension/rendering checks.

```bash
git clone https://github.com/jkindrix/html2md.git
cd html2md
poetry install --with dev --sync
poetry check
```

Keep changes focused and add behavior-based tests at the narrowest practical
boundary. Do not weaken destination validation, response limits, credential
scope, atomic writes, or the coverage floor to make a change pass. Never add
real credentials, browser databases, storage-state files, or private page
content as fixtures.

## Canonical gates

Run these before opening a pull request:

```bash
poetry run pytest src/html2md/tests tests/config \
  --cov=html2md --cov-report=term-missing:skip-covered
poetry run ruff check src/html2md tests/config
poetry run black --check src/html2md tests/config
poetry run mypy src/html2md tests/config
poetry run bandit -r src/html2md -x src/html2md/tests -ll
poetry export --only main --extras render --without-hashes \
  --format requirements.txt --output .tmp/render-requirements.txt
poetry run pip-audit --requirement .tmp/render-requirements.txt
poetry run twine check dist/*  # after `poetry build`, for packaging changes
node --test extension/tests/*.test.js
CHROME_BIN=/usr/bin/chromium node extension/tests/chromium-smoke.js
```

The Chromium command may use a platform-specific binary path. Browser-render
end-to-end tests additionally require the `render` extra and
`HTML2MD_RUN_RENDER_E2E=1`.

## Pull requests

Describe the user-visible contract, security implications, tests run, and any
documentation or changelog updates. Preserve unrelated worktree changes. A
green check does not authorize a package upload, tag, release, or Web Store
submission; those remain explicit maintainer actions.

For suspected vulnerabilities, do not open a public issue. Follow
[`SECURITY.md`](https://github.com/jkindrix/html2md/blob/main/SECURITY.md).
