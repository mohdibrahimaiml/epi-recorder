# Licensing

This repository and the paid product are licensed differently. The split is
deliberate: the trust layer is free so a customer can check a file without
asking EPI Labs for permission.

## Apache-2.0 - this repository, 4.10.0 and later

Everything in this repository is licensed under the **Apache License, Version
2.0** (`LICENSE`, with attribution in `NOTICE`). That includes:

- the `.epi` format and the verifier;
- the recorder, viewer, gateway and integrations;
- the customer-side witness receiver (`epi witness serve` / `epi witness report`);
- `epi approvers`, `epi review`, single-user `epi oversight report`;
- `epi org bundle` (create and verify the customer's own key history);
- the `epi cloud` client and the witness protocol.

Apache-2.0 grants every user a perpetual, royalty-free copyright licence **and
an explicit patent licence**, on the same terms for everyone. It adds two
obligations MIT did not have: carry the `NOTICE` file forward, and mark files
you modified. Neither asks anyone to publish their changes.

## MIT - 4.9.0 and earlier

Versions up to and including **4.9.0** were published under the MIT License.
Those grants are permanent: this change cannot revoke them, and anyone may keep
using, copying, modifying and forking those versions under MIT. That is a fact
of the licence, not a policy choice. The same applies to every commit already
in the public history before this file changed.

## Proprietary - not in this repository

- **EPI Enterprise** (`epi-enterprise`): `epi audit`, `epi annex`, `epi notify`,
  `epi chat`, the `epi enterprise` kit, role bindings, and their report and
  regulatory mappings. It lives in the private repository, declares
  `LicenseRef-Proprietary`, carries a proprietary `LICENSE`, and is marked
  `Private :: Do Not Upload`.
- **EPI Cloud**, the hosted service: accounts, witness hosting, trust pages,
  retention, billing and admin.

Neither is published to PyPI. The public wheel contains no premium module; a
boundary test fails the build if one is added to the package allowlist.

## Why the free part is not closed

The promise is that a customer, an auditor or a regulator can verify a file
without a licence, an account or a network call. That promise is only credible
if the verifier is genuinely open. Closing the public core would break the one
thing the paid product depends on: the customer's ability to check the vendor's
evidence independently.

## Contributions

By opening a pull request you agree that your contribution is licensed under
the Apache License, Version 2.0, for this repository, and you confirm you have
the right to license it that way. Do not contribute code you cannot license
that way, and do not copy code from a project whose licence is incompatible
with Apache-2.0 (for example GPLv2-only code).

## Questions

Licensing and commercial terms: `mohdibrahim@epilabs.org`.
