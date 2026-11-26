# Releasing epi-recorder

**4.11.2 status (26 Nov 2026): published.** Fixes the frozen Windows build: `epi demo` and
the `epi dev` verify/view steps re-entered the CLI through `sys.executable`, so `epi demo` failed
with "No such command '...demo_refund.py'" in the installer.

  - Tag `v4.11.2` on `9cbe69d8`; GitHub Release published.
  - PyPI wheel and sdist, with PEP 740 attestations; both provenance URLs return 200.
  - `sbom.cdx.json` (CycloneDX 1.6, 59 components).
  - `epi-setup-4.11.2.exe`, `SHA256SUMS.txt`, and Sigstore bundles
    (`epi-setup-4.11.2.exe.sigstore.json`, `SHA256SUMS.txt.sigstore.json`).
  - Not Authenticode-signed: SignPath Foundation approval is still pending, so Windows
    SmartScreen still shows "unknown publisher".

The first installer run for this tag attached no bundles: the attach step globbed `*.sigstore`
while the action writes `*.sigstore.json`. Fixed in #335, which also fails the job when no
bundle is produced; the installer workflow was then re-run for `v4.11.2`.

**4.11.1 status (26 Nov 2026): published.** Tag `v4.11.1`, GitHub Release, and the PyPI upload
with PEP 740 attestations. No Windows installer asset was published for it.

**4.11.0 status (23 Nov 2026): published.** The **Cut release** workflow
created tag `v4.11.0` on commit `6cbd13c9` and the GitHub Release (notes from
CHANGELOG.md); **Publish to PyPI (Trusted Publishing)** was then run for that
tag and uploaded the wheel and sdist. Both provenance endpoints return HTTP
200 (PEP 740 attestations), and a clean `pip install epi-recorder` installs
4.11.0. The tag is **not signed** with the maintainer SSH key (the session that
cut it had no access to it); sign future tags locally if that matters for a
reviewer. SBOM and the Windows installer were run for the tag afterwards.

**4.10.0 status (12 Nov 2026): published.** Tag `v4.10.0` is signed with the
maintainer SSH key on commit `6aad0929`; the GitHub Release triggered
`.github/workflows/publish-pypi.yml`, which uploaded the wheel and sdist with
PEP 740 attestations. The public tool is Apache-2.0 from this release; 4.9.0
and earlier remain MIT. `pip install epi-recorder==4.10.0` serves it. Verify
the tag locally with a configured `gpg.ssh.allowedSignersFile`; without one,
`git tag -v` reports that the file is missing even though the tag is signed.

**4.9.0 status (1 Nov 2026): cut, tagged `v4.9.0`, and uploaded through Trusted
Publishing** — the same path as 4.8.0, so both files carry PEP 740 attestations.
The tag is signed by the maintainer (`git tag -v v4.9.0`). It adds
`epi oversight report` (period-shaped: outcomes, models, approvals, delivery
gaps), the witness log in the browser verifier, one offer at one price on the
site, and an oversight total that leaves out files which are not the version the
customer's log recorded.

**4.8.0 status (30 Oct 2026): published through Trusted Publishing**, with
**PEP 740 attestations** on both files (provenance endpoints return HTTP 200).
The tag `v4.8.0` is signed with the maintainer's SSH key
(`git tag -v v4.8.0` against `gpg.ssh.allowedSignersFile`). It restores the
tool-call decision to the sealed record - 4.7.0 does not - and fixes the
browser verifier that called every approved file tampered.

**4.7.0 status (28 Oct 2026): published through Trusted Publishing**, with
**PEP 740 attestations** on both files (the wheel and the sdist provenance
endpoints return HTTP 200). It is the first release that shipped through this
workflow. **4.6.3** is still on PyPI and has **no PEP 740 attestations** (its
provenance endpoint returns HTTP 404): it was uploaded with the project API token
after the 4.6.2 `invalid-publisher` failure. Do not treat 4.6.3 as an attested
release. The one-time publisher setup below is the reason this worked — do not
undo it.

## One-time setup (founder, ~3 minutes)

1. Log in to pypi.org → **Your projects** → `epi-recorder` → **Manage** →
   **Publishing** → **Add a new publisher (GitHub)**.
2. Enter exactly:
   - Owner: `mohdibrahimaiml`
   - Repository: `epi-recorder`
   - Workflow name: `publish-pypi.yml`
   - Environment name: `pypi`
3. Click **Add**.
4. Go to **Account settings → API tokens** and **delete every token**
   for this project (Trusted Publishing replaces them).

The 20 Oct 2026 GitHub Release `v4.6.2` built the wheel and passed
`twine check`, then failed upload with `invalid-publisher` (OIDC token valid,
no matching publisher on PyPI). Those four fields now exist — 4.7.0 published
with attestations on 28 Oct 2026 — so a failure here again means the publisher
was changed or removed on pypi.org. Do not use the token path again for future
releases: 4.6.3 was uploaded by token only because the publisher was still
unconfigured, and that is why it has no attestations.

**The published 4.6.2 wheel has no PEP 740 attestations.** Its PyPI
provenance endpoint returns HTTP 404
(`https://pypi.org/integrity/epi-recorder/4.6.2/epi_recorder-4.6.2-py3-none-any.whl/provenance`),
because that upload did not come from this Trusted Publishing workflow. The
exact upload path was not recorded. Treat 4.6.2 and 4.6.3 as unattested.
4.7.0 is the first release published through the workflow above and it shows
**Attestations** on PyPI.

## Every release (example: v4.7.0)

1. Make sure `main` is green and `CHANGELOG.md` has the version section dated.
   If any shipped sample was rebuilt, re-seal it at the current spec, then run
   these three, in order:

   ```bash
   python scripts/refresh_demo_pinned_hashes.py   # size + SHA-256 on /verify and its mirrors
   python scripts/refresh_verify_pins.py          # the three key fingerprints /verify prints
   python scripts/sync_website.py                 # copy website/ to site/, epi-official/, verify_portal/
   ```

   The demo generator mints fresh keys on every run — it needs the private
   halves to sign — so `/verify` shows stale fingerprints unless the pins are
   refreshed from the shipped `.pub` files. Never hand-edit those numbers.
   `tests/test_demo_trust_page.py` and `tests/test_verify_demo_commands.py`
   fail on drift, so a missed step is caught before tagging.
2. **Version-bump PRs merge only when you are about to publish.** The site
   deploys on merge, so a merged bump advertises the release immediately —
   do not merge a website version bump days before the release, or the
   banner will claim a version that isn't out yet.
3. GitHub → **Releases** → **Draft a new release**.
4. Tag: **`v4.7.0`** (must match `pyproject.toml`; the workflow refuses a
   mismatch), target: `main`. **Sign the tag** (`git tag -s v4.7.0 -m "…"`;
   verify with `git tag -v`). This is convention, not a gate — no workflow
   checks the signature yet, so the releaser owns it. Unsigned tags are a
   supply-chain gap.
5. Paste the CHANGELOG section for the version into the release notes.
6. Click **Publish release**.
7. Watch **Actions → Publish to PyPI (Trusted Publishing)** turn green.
   It builds from a clean checkout of the tag, runs `twine check`, and
   uploads with signed build attestations (PEP 740, on by default).
8. Confirm on pypi.org that the version shows **Attestations** on its files.
9. Watch **Actions → SBOM** turn green: `sbom.cdx.json` (CycloneDX, resolved
   environment) attaches to the same GitHub release automatically.
10. Watch **Build Windows Installer** turn green: the `.exe`, `SHA256SUMS.txt`,
    and free Sigstore bundles (`.sigstore.json`) attach to the release. A reviewer
    checks them with:

```bash
sha256sum -c SHA256SUMS.txt
pip install sigstore
# The identity names the workflow file and the ref that built the artifact.
# A release built by a tag push carries refs/tags/vX.Y.Z; one built by a manual
# workflow_dispatch carries refs/heads/main. sigstore 4.x matches --cert-identity
# exactly, so use the ref that actually built the file you are checking.
sigstore verify identity epi-setup-4.11.2.exe \
  --bundle epi-setup-4.11.2.exe.sigstore.json \
  --cert-identity "https://github.com/mohdibrahimaiml/epi-recorder/.github/workflows/build-windows-installer.yml@refs/heads/main" \
  --cert-oidc-issuer https://token.actions.githubusercontent.com
```

This proves the bytes came from this repo's CI (transparency log), not from
an impostor site. It is not Windows SmartScreen reputation — first-time
downloads may still show a SmartScreen prompt until reputation builds. Say
that honestly if a customer asks.

### Without the GitHub Release page

Either run **Actions → Cut release** with the version (it tags `main` and
creates the GitHub Release from the CHANGELOG section), or push the tag
yourself (`git push origin vX.Y.Z`). Then start **Actions → Publish to PyPI
(Trusted Publishing) → Run workflow** with that tag. A release made by Cut
release does not start other workflows (GitHub's rule for `GITHUB_TOKEN`), so
also run SBOM and Build Windows Installer with the tag. It is the same build,
the same tag/version check and the same Trusted Publishing upload with
attestations. The tag push also runs SBOM and Build Windows Installer, which
create the GitHub Release page and attach their files.

## After the upload lands (same day)

The release *state* lives in the copy, not just the number: four files say
"prepared; publish pending" until the upload exists. Flip all of them in one PR
once PyPI shows the version and its attestations.

1. `website/index.html` — change `v4.11.0 · PyPI publish pending` to
   `v4.11.0 on PyPI`. `tests/test_website_claims.py` accepts exactly one of the
   two strings, so a half-done flip fails the gate rather than shipping.
2. `README.md` — "Current release: **v4.11.0** (prepared; PyPI publish pending)"
   becomes "(published)".
3. `docs/KNOWN_LIMITATIONS.md` — "Current release line: **4.11.0**, published on
   PyPI: **4.10.0** … upload is pending" becomes published-on-PyPI 4.11.0 with
   the pending sentence removed.
4. `docs/RELEASING.md` — add the new `**4.11.0 status (date): published.**`
   block, with the tag signature and the attestation check.
5. `python scripts/sync_website.py` so `site/`, `epi-official/` and
   `verify_portal/static/` carry the same bytes.

Leaving step 1 undone is the failure this list exists to prevent: the site would
advertise a version that pip cannot install.

## Windows installer

Pushing the `v*` tag also triggers **Build Windows Installer**, which
attaches `epi-setup-<version>.exe` **plus `SHA256SUMS.txt`** to the same
GitHub release. No extra step.

Not yet configured: **Authenticode code signing** for the `.exe` (needs a
purchased certificate). Until then, `SHA256SUMS.txt` proves *which bytes*
shipped, not *who* built them — the PyPI attestations cover the Python
distribution; the exe relies on tag signature + CI transparency. Do not claim
otherwise to a customer.

## After a backend change ships in the release

If the release changes the verify portal (legacy Render share API):
Render → **epi-verify** → **Manual Deploy** → **Deploy latest commit**.

## Never

- `twine upload` from a laptop, tag pushes by hand, or pasting tokens in chat.
- Editing this file and the workflow in different PRs: they must agree
  (`tests/test_publish_workflow.py` enforces the workflow side).
