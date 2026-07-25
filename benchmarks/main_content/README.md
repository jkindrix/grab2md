# Main-content evidence corpus

This corpus records why grab2md selected its main-content extraction strategy.
It is a versioned regression and selection aid, not evidence of universal
quality across the open web. The measured decision and current limitations are
documented in [ADR 0002](../../docs/adr/0002-select-main-content-extraction.md).

Run the comparison from the repository root:

```bash
poetry run python benchmarks/main_content/benchmark.py
```

## Admitting a fixture

A fixture must:

- reproduce an observed extraction decision or regression with the smallest
  practical HTML;
- be synthetic, maintainer-authored, or accompanied by clear redistribution
  permission and provenance;
- contain no credentials, personal data, private URLs, private page content,
  tracking identifiers, or third-party copyrighted page dumps;
- declare content that must remain and boilerplate that must be rejected in
  `fixtures.json`;
- avoid live-network dependencies so canonical results remain reproducible;
- add behavioral regression assertions at the narrowest affected runtime; and
- exercise equivalent Python and extension output when the contract is shared
  by both engines.

Public bug reports are leads, not fixtures. Minimize and sanitize a report
before committing it, record what failure it represents, and preserve only the
markup needed to reproduce that failure.

## Growth priorities

Useful next cases include malformed markup, multilingual and bidirectional
documents, documentation generators, forums, commerce layouts, nested
articles, accessibility-heavy markup, complex code and tables, and responsive
images. Add cases in response to concrete failures rather than claiming a
representative corpus before one exists.

The intake path is the
[conversion-fidelity issue form](../../.github/ISSUE_TEMPLATE/conversion-fidelity.yml).
Security concerns and sensitive inputs must never use that public form.
