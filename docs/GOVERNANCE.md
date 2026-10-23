# Governance (how this project is run)

**Status:** founder-led, private beta. This page states the current reality,
not an aspiration. It changes when reality does.

## Who decides

- **Maintainer:** mohdibrahimaiml (repo owner). Final say on scope, releases,
  and security.
- **Design partners:** 5 places ([plans page](https://epilabs.org/plans)).
  Partners get founding terms and direct feedback calls; they advise, they
  do not vote.
- **Decisions with lasting cost** are recorded as [ADRs](./adr/README.md).
  If it isn't in an ADR, it was a judgment call, not a commitment.

## Near-term direction

`CHANGELOG.md` `[Unreleased]` is the near-term list, tracked in
[ROADMAP](./ROADMAP.md) (committed vs considering, no dates). There is no
other public roadmap document; a roadmap that isn't maintained is worse
than none.

## Releases

- Version in `pyproject.toml` is the truth; docs track it until the next bump.
- Releases go through the release gate (`pytest -m "not browser and not
  experimental"`), tag-vs-version refusal, and Trusted Publishing to PyPI.
  Process: [RELEASING](./RELEASING.md).
- Git tags are signed going forward (`git tag -s`; verify with `git tag -v`).

## Security

Reports to `mohdibrahim@epilabs.org` per [../SECURITY.md](../SECURITY.md)
(5-day ack, safe harbour, supported-versions table). No bug bounty.

## Commercial

EPI Labs (epilabs.org) operates EPI Cloud. Support expectations:
[SUPPORT](../SUPPORT.md). Data terms: [DPA](./DPA.md),
[SUBPROCESSORS](./SUBPROCESSORS.md), [DATA-RETENTION](./DATA-RETENTION.md).
