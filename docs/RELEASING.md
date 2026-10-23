# Releasing epi-recorder

Releases go to PyPI through **Trusted Publishing**: no tokens, no passwords.
The workflow is `.github/workflows/publish-pypi.yml` — read it before changing
anything here.

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
no matching publisher on PyPI). Until those four fields exist on
pypi.org, every `release: published` run will fail the same way. Do not
`twine upload` from a laptop as a workaround.

## Every release (example: v4.6.2)

1. Make sure `main` is green and `CHANGELOG.md` has the version section dated.
2. **Version-bump PRs merge only when you are about to publish.** The site
   deploys on merge, so a merged bump advertises the release immediately —
   do not merge a website version bump days before the release, or the
   banner will claim a version that isn't out yet.
2. GitHub → **Releases** → **Draft a new release**.
3. Tag: **`v4.6.2`** (must match `pyproject.toml`; the workflow refuses a
   mismatch), target: `main`. **Sign the tag** (`git tag -s v4.6.2 -m "…"`;
   verify with `git tag -v`). This is convention, not a gate — no workflow
   checks the signature yet, so the releaser owns it. Unsigned tags are a
   supply-chain gap.
4. Paste the CHANGELOG section for the version into the release notes.
5. Click **Publish release**.
6. Watch **Actions → Publish to PyPI (Trusted Publishing)** turn green.
   It builds from a clean checkout of the tag, runs `twine check`, and
   uploads with signed build attestations (PEP 740, on by default).
7. Confirm on pypi.org that the version shows **Attestations** on its files.
8. Watch **Actions → SBOM** turn green: `sbom.cdx.json` (CycloneDX, resolved
   environment) attaches to the same GitHub release automatically.
9. Watch **Build Windows Installer** turn green: the `.exe`, `SHA256SUMS.txt`,
   and free Sigstore bundles (`.sigstore`) attach to the release. A reviewer
   checks them with:

```bash
sha256sum -c SHA256SUMS.txt
pip install sigstore
sigstore verify epi-setup-4.6.2.exe --bundle epi-setup-4.6.2.exe.sigstore \
  --cert-identity https://github.com/mohdibrahimaiml/epi-recorder \
  --cert-oidc-issuer https://token.actions.githubusercontent.com
```

This proves the bytes came from this repo's CI (transparency log), not from
an impostor site. It is not Windows SmartScreen reputation — first-time
downloads may still show a SmartScreen prompt until reputation builds. Say
that honestly if a customer asks.

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
