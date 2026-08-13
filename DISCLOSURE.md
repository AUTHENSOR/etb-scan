# Vulnerability Disclosure Policy — Authensor, Inc.

*Applies to all AUTHENSOR repositories by default. Last updated 2026-08-13.*

Authensor finds defects in AI evaluation infrastructure: benchmark harnesses,
LLM-judge pipelines, scoring services, and the tooling around them. This
policy covers two directions of report — flaws *in our software*, and flaws
*we find in yours*.

## Reporting a vulnerability to us

Use the Security Advisories tab on the relevant repository, or email
john@authensor.com. Expect a first response within three working days.

In scope for our own software: anything that makes our tooling report an
unsafe judge as safe, or that executes unintended code during a scan.

## How we disclose vulnerabilities we find

Our research practice files defect reports publicly, upstream, with a
proposed patch — see the ledger at
[AUTHENSOR/etb-scan EVIDENCE-TABLE.md](https://github.com/AUTHENSOR/etb-scan/blob/main/EVIDENCE-TABLE.md).
Our default is full public disclosure with no embargo, because the findings
contain no non-public information and the affected artifacts are public.

Where a finding has exploitation potential beyond a defective benchmark
score (for example remote code execution with the privileges of a scoring
server), we use coordinated disclosure:

1. Report to the maintainer through their preferred channel (security
   advisory, SECURITY.md contact, or direct email), with a working
   proof of concept and a proposed fix.
2. Acknowledge reminders at 14 and 30 days.
3. Public disclosure at 90 days from first report, or when a fix ships,
   whichever comes first. We may disclose earlier if the maintainer
   agrees, or later if a fix is demonstrably in progress.

We do not disclose where doing so would expose non-public user data, and we
never name individuals in a disclosure — findings are about systems.

## Safe harbor

We will not pursue legal action against good-faith security research
conducted under this policy against our systems, and we ask the same of the
projects we research. Good faith means: no destruction of data, no access
beyond what the finding requires, no public disclosure of another party's
non-public information.

## Citation

When a finding of ours is fixed, we appreciate a mention in the release
notes or advisory. We do the same in ours.

Contact: john@authensor.com · https://www.authensor.com
