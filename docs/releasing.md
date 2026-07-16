# Release process

Releases are deliberate maintainer actions. Passing CI does not by itself
authorize publishing packages, creating remote releases, or pushing tags.

## Prepare

1. Choose the release version and move relevant `Unreleased` entries in
   `CHANGELOG.md` into a dated version section.
2. Confirm `pyproject.toml`, `html2md --version`, `python -m html2md --version`,
   wheel metadata, and extension metadata have the intended versions.
3. Recheck `html2md-cli` availability and ownership on TestPyPI and PyPI. The
   name was unregistered when checked on 2026-07-16, but that is not a
   reservation.
4. Start from a clean checkout with only the intended release commit.

## Verify and build

```bash
poetry install --with dev --sync
poetry check
poetry run pre-commit run --all-files
poetry run pre-commit run --all-files --hook-stage pre-push
node --test extension/tests/*.test.js
node extension/tests/chromium-smoke.js
./deploy.sh --dry-run
python -m pip install twine
python -m twine check dist/*
sha256sum dist/* > dist/SHA256SUMS
```

Record the commit, operating system, Python version, Poetry version, commands,
test totals, and checksums in the release notes.

## Stage and publish

1. Upload to TestPyPI and install the exact artifact in a fresh environment.
2. Exercise `html2md --help`, `html2md --version`, `python -m html2md --help`,
   local conversion, and a local-server URL conversion.
3. Obtain explicit maintainer approval for the public release.
4. Create a signed tag when signing is configured, otherwise an annotated tag:

   ```bash
   git tag -s vX.Y.Z -m "html2md-cli X.Y.Z"
   # or: git tag -a vX.Y.Z -m "html2md-cli X.Y.Z"
   ```

5. Push the approved tag, publish the already-tested artifacts to PyPI, and
   create the release using the same changelog text and checksums.
6. Install from PyPI in a new environment and repeat the entry-point smoke test.

If any artifact, version, checksum, or smoke result differs, stop the release;
do not rebuild under the same version.
