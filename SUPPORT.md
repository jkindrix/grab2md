# Support and compatibility

html2md is an alpha-stage, CLI-first project maintained on a best-effort basis.
Use GitHub issues for reproducible defects, documentation corrections, and
focused feature evidence. Include the version or commit, operating system,
Python version, exact command, sanitized input characteristics, observed
output, and relevant redacted diagnostics.

The supported pre-1.0 compatibility surface is the documented `html2md` CLI.
Internal Python imports, generated Markdown details not covered by the output
contract, browser database formats, and unpacked-extension behavior may change
between alphas. Windows, macOS, and Linux package behavior is exercised in CI;
optional Chromium rendering remains Linux-gated unless evidence justifies a
broader matrix.

There is no guaranteed response time, paid support, hosted service, stable API,
or production-readiness commitment. Security concerns must use the private
route in [`SECURITY.md`](https://github.com/jkindrix/html2md/blob/main/SECURITY.md),
not a public issue.
