# Optional JavaScript rendering

The default conversion path uses `requests` and does not execute page code.
`html2md convert --render-js` is an explicit, URL-only mode for pages whose
meaningful DOM is created by JavaScript.

## Installation

Browser automation is isolated from the base package:

```bash
python -m pip install "html2md-cli[render]"
python -m playwright install chromium
html2md convert https://example.com/app --render-js --output app.md
```

Playwright versions require matching browser binaries. Re-run the browser
installation after upgrading the render extra. The browser cache requires a few
hundred megabytes; the base/static installation downloads none of it.

## Resource and security boundary

Rendered pages execute untrusted JavaScript in a fresh, headless,
non-persistent Chromium context. The context:

- has no imported browser profile, cookies, OAuth tokens, or persistent storage;
- blocks service workers, downloads, images, media, and fonts;
- permits subresources only from the explicitly requested or navigated origin;
- permits a cross-origin top-level redirect only after all resolved addresses
  are public, preventing redirects to loopback, private, link-local, or metadata
  endpoints;
- rejects credential-bearing and non-HTTP(S) network URLs;
- caps navigation at 30 seconds, post-load settling at 500 milliseconds, and
  serialized HTML at 10 MiB; and
- closes the browser after one conversion.

`--insecure` also disables certificate verification inside Chromium and carries
the same interception risk as the static path. Browser/JSON cookie import is
rejected in render mode rather than silently creating an authenticated browser.
Downloaded images are fetched after rendering through the existing guarded
image policy, not by Chromium.

These controls reduce exposure but do not make hostile JavaScript harmless.
Chromium is a large native-code dependency and must be kept patched. Run render
mode with ordinary user privileges and avoid sensitive network environments.

## Scope

Rendering is supported by `convert` only. Batch and crawl remain static so their
single-fetch, robots, rate-limit, retry, and checkpoint contracts are not
bypassed by a second browser request. Expanding rendering to those workflows
requires a browser-backed fetch result integrated at the crawler boundary, not
an after-the-fact second fetch.

Cross-origin API-driven applications may render incompletely because their
subresource requests are blocked. This is an intentional default-deny trade-off;
there is no unrestricted-network switch.
