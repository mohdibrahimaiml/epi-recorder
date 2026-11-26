# Code signing policy

This policy covers the Windows binaries built from this repository: the
installer `epi-setup-<version>.exe` attached to GitHub Releases, and the
Microsoft Store package.

## Signing

- **Windows installer (GitHub Releases):** free code signing provided by
  [SignPath.io](https://about.signpath.io), certificate by
  [SignPath Foundation](https://signpath.org). This applies from the first
  release signed through SignPath; earlier installers were not
  Authenticode-signed.
- **Microsoft Store package:** signed by Microsoft when the Store publishes it.
- **Every release** also carries a `SHA256SUMS.txt` and Sigstore bundles, and
  the PyPI packages carry PEP 740 build attestations, so the bytes can be
  traced to the GitHub Actions run that built them.

Only binaries built by this repository's GitHub Actions workflows from its
public source are submitted for signing. Nothing built on a personal machine is
signed. The signed installer contains only open-source code; the paid
`epi-enterprise` package is not part of it.

## Team roles

| Role | Members |
|---|---|
| Committers and reviewers | [Mohd Ibrahim Afridi](https://github.com/mohdibrahimaiml) |
| Approvers | [Mohd Ibrahim Afridi](https://github.com/mohdibrahimaiml) |

Changes, including those drafted with AI coding assistants, reach `main` only
through pull requests that the maintainer reviews and merges. Every signing
request is approved by an approver. All team members use multi-factor
authentication on GitHub and SignPath.

## Privacy

This program will not transfer any information to other networked systems
unless specifically requested by the user or the person installing or operating
it. Usage telemetry is off by default and only sent if the user turns it on;
commands that upload a record (such as `epi share` and `epi cloud push`) send
it only when the user runs them. See [PRIVACY](https://epilabs.org/privacy).

## Reporting

Report a signed binary that you believe is malicious or misused to
[SECURITY.md](SECURITY.md) contacts, or to SignPath Foundation at
<https://signpath.org>.
