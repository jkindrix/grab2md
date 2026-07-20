# Coverage baseline

Coverage is measured against production code in `src/html2md`; package-internal test modules are excluded from both collection and reporting. The canonical suite includes unit, integration, and real CLI subprocess tests:

```bash
poetry run coverage erase
poetry run pytest src/html2md/tests tests/config \
  --cov=html2md --cov-report=term-missing:skip-covered
```

On 2026-07-19, Python 3.11.2 measured **4,784 production statements, 602
missed, and 87.42% total coverage** (`476 passed, 4 skipped`) on the remediation
working tree based on `1140c269`. The enforced floor is 85%, preserving an
interpreter-dependent buffer without allowing coverage to fall far below the
earlier stabilization baseline. The floor must not be lowered merely to make a
change pass.

The denominator differs from the pre-remediation 4,773-statement review
snapshot because command callbacks, crawler setup, batch stages, and image
redirect handling were decomposed or consolidated. New typed command/runtime
boundaries and tests were added at the same time; this is a structural change,
not exclusion of production modules from measurement.

The largest gaps are concentrated in:

| Module | Statements | Missed | Coverage | Tracked work |
|---|---:|---:|---:|---|
| `cli/cli.py` | 201 | 64 | 68% | Keep callbacks limited to option translation, rendering, and exit status |
| `cli/command_runtime.py` | 154 | 4 | 97% | Preserve direct presentation-neutral command tests |
| `cli/conversion_presenter.py` | 53 | 10 | 81% | Preserve success/failure/output presentation fixtures |
| `cli/config_commands.py` | 238 | 37 | 84% | Add remaining interactive/error fixtures |
| `cookies/session_manager.py` | 291 | 84 | 71% | Add supported Windows DPAPI fixtures on hosted Windows as formats evolve |
| `network/browser_renderer.py` | 143 | 10 | 93% | Preserve lifecycle, policy, budget, and cleanup fixtures |
| `network/safe_http.py` | 258 | 29 | 89% | Preserve shared buffered/streaming policy fixtures |

The post-alpha 75% target has been exceeded; an 85% regression floor now
ratchets the verified baseline. New or changed behavior should receive focused
tests even when repository-wide coverage remains
above the floor.
