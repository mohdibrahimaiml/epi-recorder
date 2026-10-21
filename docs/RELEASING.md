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

## Every release (example: v4.6.1)

1. Make sure `main` is green and `CHANGELOG.md` has the version section dated.
2. **Version-bump PRs merge only when you are about to publish.** The site
deploys on merge, so a merged bump advertises the release immediately —
do not merge a website version bump days before the release, or the
banner will claim a version that isn't out yet.
2. GitHub → **Releases** → **Draft a new release**.
3. Tag: **`v4.6.1`** (must match `pyproject.toml`; the workflow refuses a
   mismatch), target: `main`.
4. Paste the CHANGELOG section for the version into the release notes.
5. Click **Publish release**.
6. Watch **Actions → Publish to PyPI (Trusted Publishing)** turn green.
   It builds from a clean checkout of the tag, runs `twine check`, and
   uploads with signed build attestations (PEP 740, on by default).
7. Confirm on pypi.org that the version shows **Attestations** on its files.

## Windows installer

Pushing the `v*` tag also triggers **Build Windows Installer**, which
attaches `epi-setup-<version>.exe` to the same GitHub release. No extra step.

## After a backend change ships in the release

If the release changes the verify portal (legacy Render share API):
Render → **epi-verify** → **Manual Deploy** → **Deploy latest commit**.

## Never

- `twine upload` from a laptop, tag pushes by hand, or pasting tokens in chat.
- Editing this file and the workflow in different PRs: they must agree
  (`tests/test_publish_workflow.py` enforces the workflow side).
