# Extension vendored-asset maintenance

The extension intentionally ships two third-party JavaScript assets so it can
operate locally without runtime package or network dependencies:

- `readability.js` is an unmodified, SHA-256-pinned copy of Mozilla Readability
  0.6.0.
- `turndown.js` is a maintained derivative whose recorded upstream baseline is
  Turndown 7.1.1.

The Turndown file must not be replaced blindly with a newer distribution.
GRAB2MD's derivative has security and output contracts that differ from
upstream, including inert `DOMParser` parsing, authored Markdown escaping,
table conversion, code-fence sizing, and popup-specific rules.

## Upstream review procedure

Perform this review before an extension release and whenever an upstream
security or correctness release is reported:

1. Select the last reviewed upstream tag from
   `THIRD_PARTY_NOTICES.md` and the candidate tag from Turndown's official
   release page.
2. Record each package's registry integrity value with
   `npm view turndown@VERSION dist.integrity`.
3. Download both packages without lifecycle scripts into a temporary directory:

   ```bash
   review_dir="$(mktemp -d)"
   npm pack turndown@7.1.1 --ignore-scripts --pack-destination "$review_dir"
   npm pack turndown@CANDIDATE --ignore-scripts --pack-destination "$review_dir"
   ```

4. Compare the two upstream browser builds and release notes. Classify every
   production change as applicable, already superseded locally, or irrelevant
   to the browser derivative. Review source commits when a generated-build diff
   is ambiguous.
5. Port applicable changes narrowly. Preserve inert parsing and the extension's
   explicit output contract; add a behavioral regression for every port instead
   of relying on source-text similarity.
6. Run the complete extension evidence:

   ```bash
   for file in extension/*.js extension/tests/*.js; do node --check "$file"; done
   node --test extension/tests/*.test.js
   node extension/tests/chromium-smoke.js
   ```

7. Update `THIRD_PARTY_NOTICES.md` with the candidate tag, review date, accepted
   ports, explicit non-ports, provenance, and any license changes. If the
   derivation baseline itself changes, update every baseline reference and
   re-audit the complete local diff.

For Readability updates, additionally compare the published source byte-for-byte,
update its SHA-256 and version together, reproduce the Apache-2.0 notice, and run
all three article/full-page/selection Chromium paths.

## Current review

On 2026-07-24, Turndown releases from the 7.1.1 baseline through 7.2.4 were
reviewed. GRAB2MD incorporates the relevant link/image destination and title
escaping, ordered-list continuation indentation, object-property guard, and
linear trailing-newline trimming. Upstream 7.2.3's `<pre>` line-ending
normalization was reverted in 7.2.4; the local derivative instead retains its
stronger runtime contract that authored indentation, blank lines, tabs, and
backtick runs remain unchanged.
