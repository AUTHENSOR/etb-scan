# Releasing

Publishing runs on a `v*` tag push via
[`.github/workflows/publish.yml`](.github/workflows/publish.yml). There is no
API token in this repo or in GitHub secrets, and there never should be.

## One-time PyPI setup

Do this once, signed in as the account that will own the project.

### 1. Enable 2FA if it is not already on

<https://pypi.org/manage/account/two-factor/>

Trusted Publishing will not work without it, and it is required to create a
project regardless.

### 2. Create a *pending* publisher

<https://pypi.org/manage/account/publishing/>

`etb-scan` does not exist on PyPI yet, so this is a "pending" publisher rather
than a setting on an existing project. Fill in exactly:

| Field | Value |
|---|---|
| PyPI Project Name | `etb-scan` |
| Owner | `AUTHENSOR` |
| Repository name | `etb-scan` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

The environment name is not optional here: the workflow declares
`environment: name: pypi`, and PyPI checks the claim. A mismatch fails the
upload with a confusing permissions error.

**A pending publisher does not reserve the name.** PyPI is explicit that it
does not create or hold the project until something is actually published.
Until the first successful upload, `etb-scan` is available to anyone.

### 3. Optionally require approval before a publish

<https://github.com/AUTHENSOR/etb-scan/settings/environments>

Create an environment named `pypi` and add yourself as a required reviewer.
The publish job then waits for a manual approval before it can mint the OIDC
token. Worth doing: it is the only human checkpoint between a pushed tag and an
irreversible upload.

## Cutting a release

```bash
# 1. bump both, they must agree
#    pyproject.toml    version = "0.1.1"
#    etbscan/__init__.py  __version__ = "0.1.1"

python3 -m pytest -q                 # must be green
python3 -m build && twine check --strict dist/*

git commit -am "etb-scan 0.1.1"
git tag -a v0.1.1 -m "etb-scan 0.1.1"
git push origin main --follow-tags
```

The tag push triggers build, tests on 3.9 and 3.13, then publish.

## Things that bite

**A version number is spent the moment it uploads.** PyPI allows yanking but
never re-uploading the same version. If `0.1.0` ships broken, the fix is
`0.1.1`. This is why the workflow runs the test suite on the tag rather than
trusting that CI passed on `main`.

**Test the whole path first.** TestPyPI takes its own separate pending
publisher at <https://test.pypi.org/manage/account/publishing/>, with the same
five fields. Add `repository-url: https://test.pypi.org/legacy/` to the publish
step to rehearse against it.

**`etbscan` unhyphenated needs no defending.** PEP 503 normalization
collapses runs of `-_.` without deleting them, so `etb-scan` and `etbscan`
resolve as two distinct names, and our import name and console script are both
`etbscan`. That looked like a squat risk. It is not: PyPI applies a separate
"ultranormalization" similarity check when a project is first created, and
registering `etbscan` now fails with *"This project name is too similar to an
existing project."* Verified against the live form. That guard applies to
everyone, so publishing `etb-scan` first is itself the defence, and a stub
package would be unpublishable anyway.

## GitHub Actions Marketplace

Separate from PyPI, and also one-time. `action.yml` is already at the repo root
and the name "ETB Scan" is unclaimed.

1. Accept the Marketplace Developer Agreement (the publish checkbox stays
   greyed out until the owning account has).
2. Draft a release at
   <https://github.com/AUTHENSOR/etb-scan/releases/new> and tick
   **Publish this Action to the GitHub Marketplace**.
3. Pick a primary and secondary category.

No review queue; listings go live immediately once the requirements are met.
