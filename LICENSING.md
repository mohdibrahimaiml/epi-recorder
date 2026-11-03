# Licensing

This repository and the paid product are licensed differently. The split is
deliberate: the trust layer is free so a customer can check a file without
asking EPI Labs for permission.

## MIT — this repository

Everything in this repository is MIT-licensed. That includes:

- the `.epi` format and the verifier;
- the recorder, viewer, gateway and integrations;
- the customer-side witness receiver (`epi witness serve` / `epi witness report`);
- `epi approvers`, `epi review`, single-user `epi oversight report`;
- `epi org bundle` (create and verify the customer's own key history);
- the `epi cloud` client and the witness protocol.

**Published versions stay MIT.** Releases up to and including 4.9.0 were
published under MIT. Changing this repository now would not revoke that grant
for those versions; anyone may keep using, copying and forking them under MIT.
That is a fact of the licence, not a policy choice.

## Proprietary — not in this repository

- **EPI Enterprise** (`epi-enterprise`): `epi audit`, `epi annex`, `epi notify`,
  `epi chat`, the `epi enterprise` kit, role bindings, and their report and
  regulatory mappings. It lives in the private repository, declares
  `LicenseRef-Proprietary`, carries a proprietary `LICENSE`, and is marked
  `Private :: Do Not Upload`.
- **EPI Cloud**, the hosted service: accounts, witness hosting, trust pages,
  retention, billing and admin.

Neither is published to PyPI. The public wheel contains no premium module; a
boundary test fails the build if one is added to the package allowlist.

## Why the free part is not relicensed

The promise is that a customer, an auditor or a regulator can verify a file
without a licence, an account or a network call. That promise is only credible
if the verifier is genuinely open. Relicensing the public core would break the
one thing the paid product depends on: the customer's ability to check the
vendor's evidence independently.

## Contributions

By opening a pull request you agree that your contribution is licensed under
the MIT License for this repository. Do not contribute code you cannot license
that way.

## Questions

Licensing and commercial terms: `mohdibrahim@epilabs.org`.
