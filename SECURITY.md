# Security

## Reporting a vulnerability in etb-scan

Use [GitHub Security Advisories](https://github.com/AUTHENSOR/etb-scan/security/advisories/new),
not a public issue. Or email <john@authensor.com>.

Expect a first response within three working days.

`etb-scan` is offline and stdlib-only: no network, no API keys, no model spend,
no runtime dependencies. That removes most of the usual surface. What remains:

- It loads and calls **your** judge callable via a dotted path (`--judge`), so
  it executes code you point it at. Do not point it at untrusted code.
- It parses a JSON corpus, which you can replace with your own.
- The pytest, Inspect, pre-commit and Action surfaces all run it in CI, where a
  wrong exit code has consequences. **A scan that reports a broken judge as
  clean is a security bug in this tool**, not a papercut. Report it as one.

## The far more likely case: a defect in your evaluator

If you scanned a judge and it came back exploitable, the finding is about your
system, not this one. Nothing is reported to us. There is no telemetry.

We would rather you filed it upstream with the maintainers of whatever
framework you found it in, the way the 76 instances in
[`EVIDENCE-TABLE.md`](EVIDENCE-TABLE.md) were filed: publicly, with a proposed
patch. Every one of those was disclosed with no embargo, because none of them
contained non-public information.

If it would help to have the class described in writing for that conversation,
point the maintainers at <https://www.authensor.com/etb>. The per-class anchors
are stable and meant to be cited in someone else's issue tracker.

## Scope

In scope: anything that makes this tool report an unsafe judge as safe, or that
executes unintended code during a scan.

Out of scope: the detector's deliberate low recall. It is high-precision by
design, catching roughly 28% of corpus injections when used as a general
detector, because chasing recall made it fire on 53% of honest technical
answers. A missed attack is a known limitation, documented in the README. A
false clean bill of health is not.
