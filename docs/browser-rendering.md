# Optional JavaScript rendering

The default conversion path uses `requests` and does not execute page code.
`grab2md URL --render-js` is an explicit, URL-only mode for pages whose
meaningful DOM is created by JavaScript.

## Installation

Browser automation is isolated from the base package:

```bash
python -m pip install "grab2md[render]"
python -m playwright install chromium
grab2md https://example.com/app --render-js --output app.md
```

Pages that load code or data from another origin require each origin to be
authorized explicitly. Pages whose content remains behind disclosure controls
also require an explicit Playwright selector to click:

```bash
grab2md https://alex.draftist.io/blog/the-bedrock-of-software-design-ycqvcedsj \
  --render-js \
  --render-origin https://cdn.draftist.app \
  --wait-for-selector main \
  --click-selector 'figure button:has(h2)' \
  --output article.md
```

Render origins and click selectors are repeatable. A render origin must be an
exact HTTP(S) origin; paths, queries, fragments, and embedded credentials are
rejected. `--wait-for-selector` accepts one Playwright selector and waits for it
to be attached before clicks and snapshotting. Each click selector clicks every
matching element once in document order. A missing readiness or click match
fails the conversion instead of silently returning an incomplete snapshot.

For troubleshooting, `--log-level INFO --debug-log render.log` records the
request and transfer counts, each explicit selector's match count, and the
origins blocked by the default-deny route policy. Blocked-origin diagnostics
contain origins rather than full request URLs so query data is not exposed.

For a page requiring an existing browser session, create Playwright storage
state in a separate login process, restrict it to the current user, and pass it
explicitly:

```bash
chmod 600 session-state.json
grab2md https://example.com/app --render-js \
  --storage-state session-state.json
```

Playwright versions require matching browser binaries. Re-run the browser
installation after upgrading the render extra. The browser cache requires a few
hundred megabytes; the base/static installation downloads none of it.

## Resource and security boundary

Rendered pages execute untrusted JavaScript in a fresh, headless Chromium
context. By default the context is non-persistent; `--storage-state` can seed it
from an owner-only Playwright state file created by a separate login process.
The context:

- never modifies the supplied storage-state file and does not persist resulting
  cookies or local storage;
- blocks service workers, downloads, images, media, and fonts;
- resolves the requested hostname once, validates every returned address, and
  pins Chromium to one validated numeric address while retaining the URL
  hostname for HTTP and TLS identity;
- permits subresources only from the requested origin and origins explicitly
  authorized with `--render-origin`, while stripping credentials from those
  additional origins and blocking cross-origin top-level redirects;
- fails all other Chromium DNS lookups and bypasses system proxy resolution;
- rejects credential-bearing and non-HTTP(S) network URLs;
- blocks HTTP methods other than GET, HEAD, and OPTIONS throughout navigation,
  hydration, settling, and explicit interaction;
- blocks WebSockets before their network handshake is established;
- caps navigation at 30 seconds, settling before and after explicit clicks at
  500 milliseconds, explicit clicks at 25, aggregate decoded browser response
  data at 50 MiB, requests at 250, and serialized HTML at 10 MiB; and
- closes the browser after one conversion.

During explicit clicks, grab2md also blocks top-level navigation. Selectors
should still target disclosure controls rather than general buttons: a click
can run arbitrary page code, issue permitted GET/HEAD requests, and mutate the
temporary browser DOM or storage. Use authenticated storage state only when the
selected controls and page are trusted.

Private, loopback, link-local, and metadata source destinations are rejected by
default. `--allow-private-network` explicitly permits a trusted internal or
local source while retaining hostname pinning and the remaining controls.
`--insecure` also disables certificate verification inside Chromium and carries
the same interception risk as the static path. Browser/JSON cookie import is
rejected in render mode rather than silently creating an authenticated browser.
Downloaded images are fetched after rendering through the existing guarded
image policy, not by Chromium.

These controls reduce exposure but do not make hostile JavaScript harmless.
Chromium is a large native-code dependency and must be kept patched. Run render
mode with ordinary user privileges and avoid sensitive network environments.

## Scope

Rendering is supported by direct URL conversion only. Batch and crawl remain
static so their single-fetch, robots, rate-limit, retry, and checkpoint
contracts are not bypassed by a second browser request. Expanding rendering to
those workflows requires a browser-backed fetch result integrated at the
crawler boundary, not an after-the-fact second fetch.

Cross-origin redirects and API-driven applications may render incompletely
unless every required subresource origin is authorized explicitly. Applications
that require POST or another mutating method during initial hydration fail the
render rather than sending that request, and WebSocket-dependent applications
cannot use that channel. These are intentional default-deny trade-offs;
`--allow-private-network` changes address classification only and is not an
unrestricted cross-origin switch.

No automatic "expand everything" heuristic is applied. Generic buttons can
submit forms or change remote state, and framework-specific hydration data is
not treated as visible article content. Use `--click-selector` only for controls
whose behavior is understood.
