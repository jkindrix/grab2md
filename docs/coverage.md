# Coverage baseline

Coverage is measured against production code in `src/html2md`; package-internal test modules are excluded from both collection and reporting. The canonical suite includes unit, integration, and real CLI subprocess tests:

```bash
poetry run coverage erase
poetry run pytest src/html2md/tests tests/config \
  --cov=html2md --cov-report=term-missing:skip-covered
```

On 2026-07-17, Python 3.11.2 measured 4,554 production statements, 1,352
missed, and 70.31% total coverage. The enforced floor is 65%, preserving a
small interpreter-dependent buffer without allowing coverage to fall back to
the earlier stabilization baseline. The floor must not be lowered merely to
make a change pass.

The largest gaps are concentrated in:

| Module | Statements | Missed | Coverage | Tracked work |
|---|---:|---:|---:|---|
| `utils/progress_display.py` | 151 | 151 | 0% | Remove if obsolete or add presentation tests |
| `cli/config_commands.py` | 310 | 199 | 36% | Add command error/interaction fixtures |
| `cookies/session_manager.py` | 477 | 296 | 38% | Add platform/backend boundary fixtures |
| `network/browser_renderer.py` | 103 | 47 | 54% | Extend optional-browser policy/error fixtures |

The current alpha baseline does not claim 75% coverage. Seventy-five percent is
a post-alpha improvement target, not a completed stabilization release gate.
New or changed behavior should receive focused tests even when repository-wide
coverage remains above the enforced floor.
