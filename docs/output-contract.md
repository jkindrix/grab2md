# Markdown output contract

`html2md` converts the fetched or local HTML document to Markdown. Existing
content behavior remains the default; metadata front matter is opt-in with
`--metadata` on `convert`, `batch`, and `crawl`.

## URLs

For HTTP(S) documents, relative Markdown links and image references are resolved
against the final response URL. A valid HTML `<base href>` overrides that base
for document references. Root-relative, path-relative, protocol-relative,
query, and fragment components follow standard URL joining rules. Fragment-only
links and non-web schemes such as `mailto:` remain unchanged.

This canonicalization occurs before image downloading and archive link
rewriting. Downloaded image references can therefore be replaced by local image
paths, and successful crawl/batch targets can still be rewritten relative to
the containing Markdown file.

Local HTML references are not canonicalized. They remain source-relative so
local links retain their meaning and the guarded local-image copier can resolve
them beneath the source document directory.

## Metadata

With `--metadata`, output starts with YAML-compatible front matter. Populated
fields appear in this fixed order:

```yaml
---
title: "Page title"
author: "Author name"
date: "2026-07-16T10:30:00Z"
canonical_url: "https://example.com/article"
description: "Page description"
language: "en-US"
---
```

All values are JSON-quoted strings, which are also valid YAML scalars. Missing
fields are omitted. Extraction uses standard HTML title, meta, canonical-link,
and language attributes. Open Graph/Twitter title and description fields and
article publication fields are recognized. For a remote document without an
explicit canonical link, `canonical_url` is the final response URL. Local files
do not receive a fabricated canonical URL.

The contract deliberately does not infer missing authors or dates from page
text and does not execute JSON-LD. This keeps output deterministic and avoids
turning ambiguous heuristics into asserted metadata.
