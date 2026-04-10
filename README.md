# BSR Python SDK + uv `exclude-newer` Incompatibility

Minimal reproduction of a dependency-resolution failure that occurs when using
[uv](https://docs.astral.sh/uv/)'s `exclude-newer` feature together with BSR-hosted
Python SDKs (`https://buf.build/gen/python`).

---

## Background

### What is `exclude-newer`?

`exclude-newer` is a uv security feature that prevents installing packages published
after (or without) a known timestamp. Teams use it as a supply-chain guard against
dependency confusion attacks — a malicious package backdated to look older than a
legitimate pin would be rejected.

When `exclude-newer = "30d"` is set, uv only allows packages whose index entry
includes a publish timestamp that falls within the last 30 days. If a package has
**no timestamp**, uv rejects it entirely.

### How uv fetches timestamps

uv uses the **PEP 691 JSON Simple API** to retrieve timestamps. It sends:

```
Accept: application/vnd.pypi.simple.v1+json
```

A compliant index returns JSON with an `upload-time` field per file (defined by
[PEP 700](https://peps.python.org/pep-0700/)):

```json
{
  "files": [
    {
      "filename": "grpcio-1.80.0.tar.gz",
      "upload-time": "2015-03-30T23:24:33.390776Z"
    }
  ]
}
```

---

## Root Cause

BSR implements [PEP 503](https://peps.python.org/pep-0503/) (HTML Simple API) but
does not implement the [PEP 691](https://peps.python.org/pep-0691/) JSON Simple API.
When uv sends `Accept: application/vnd.pypi.simple.v1+json`, BSR ignores the header
and returns `text/html`.

**PyPI (works):**
```
$ curl -sI -H "Accept: application/vnd.pypi.simple.v1+json" \
    https://pypi.org/simple/grpcio/ \
  | grep content-type

content-type: application/vnd.pypi.simple.v1+json
```

**BSR (broken):**
```
$ curl -sI -H "Accept: application/vnd.pypi.simple.v1+json" \
    https://buf.build/gen/python/simple/beta-googleapis-grpc-python/ \
  | grep content-type

content-type: text/html
```

PEP 700 only defines `upload-time` for the JSON format — the HTML Simple API has no
equivalent. Without timestamps, uv rejects every BSR wheel when `exclude-newer` is set.

---

## Reproducing the Error

**Prerequisites:** [uv](https://docs.astral.sh/uv/getting-started/installation/) ≥ 0.4

```bash
git clone https://github.com/saefty/test-bsr-metadata
cd test-bsr-metadata
uv sync
```

The repo has `exclude-newer = "30d"` and depends on
[`beta-googleapis-grpc-python`](https://buf.build/gen/python/simple/beta-googleapis-grpc-python/)
— a real BSR-generated gRPC SDK for the Google APIs proto package.

**Expected output** (the date shown is always 30 days before the time you run it):

```
warning: beta_googleapis_grpc_python-1.80.0.1...whl is missing an upload date,
         but user provided: <30-days-ago>
  (repeated for every BSR wheel — ~94 warnings)

× No solution found when resolving dependencies:
╰─▶ Because there are no versions of beta-googleapis-grpc-python and your
    project depends on beta-googleapis-grpc-python, we can conclude that
    your project's requirements are unsatisfiable.

    hint: `beta-googleapis-grpc-python` was filtered by `exclude-newer`
    to only include packages uploaded before <30-days-ago>.
    Consider using `exclude-newer-package` to override the cutoff for this
    package.
```

Note: `grpcio` (from PyPI) resolves without errors because PyPI implements the
JSON API and provides `upload-time`.

---

## Why the Obvious Workarounds Don't Work

### `exclude-newer-package = { beta-googleapis-grpc-python = false }` (uv ≥ 0.9.25)

This disables the timestamp check for the named package, but the check still applies
to **transitive deps**. `beta-googleapis-grpc-python` pulls in
`beta-googleapis-protocolbuffers-python` — also from BSR, also without timestamps.
uv then iterates all ~112 candidate versions of that package looking for timestamps,
generates 112 more warnings, and fails again. You would have to manually enumerate
every BSR package in the full dep tree, and the check would run through hundreds of
wheel files before failing, making resolution hang for minutes.

### `exclude-newer-package = { pkg = "2100-01-01" }` (a future date)

A per-package date override does not bypass missing-timestamp rejection. uv still
rejects wheels with no timestamp regardless of what cutoff date is set.

---

## Workarounds Available Today

### Option A — Per-index disable (uv preview, next stable release after 2026-04-08)

[astral-sh/uv#18839](https://github.com/astral-sh/uv/pull/18839) added `exclude-newer`
as a per-index setting. Until it ships in a stable uv release, it requires preview mode:

```toml
[tool.uv]
exclude-newer = "30d"
preview = true

[[tool.uv.index]]
url = "https://buf.build/gen/python"
name = "buf-bsr"
exclude-newer = false
```

**Security trade-off:** This disables the supply-chain guard specifically for BSR
packages while keeping it active for PyPI. The assumption is that BSR's own integrity
guarantees are trusted for packages sourced from it.

### Option B — Remove `exclude-newer` globally

Omit `exclude-newer` entirely from any project that depends on BSR packages. This is
the only broadly working mitigation today without a preview uv build.

**Security trade-off:** Removes the timestamp guard for all packages including PyPI.

---

## The Fix

BSR should implement content negotiation for the PEP 691 JSON Simple API:

1. When a client sends `Accept: application/vnd.pypi.simple.v1+json`, respond with
   `Content-Type: application/vnd.pypi.simple.v1+json`
2. Return the [PEP 691 JSON format](https://peps.python.org/pep-0691/#project-detail)
   with an `upload-time` field (ISO 8601 UTC) for each file entry

This is additive — existing HTML clients continue to work unchanged. Any tool that
uses PEP 700 timestamps (not just uv) would benefit.

**Relevant specs:**
- [PEP 503](https://peps.python.org/pep-0503/) — HTML Simple API (what BSR implements today)
- [PEP 691](https://peps.python.org/pep-0691/) — JSON Simple API with content negotiation
- [PEP 700](https://peps.python.org/pep-0700/) — `upload-time` field definition

**Related uv issues (for context):**
- [astral-sh/uv#12449](https://github.com/astral-sh/uv/issues/12449) — skip packages without publish date
- [astral-sh/uv#16813](https://github.com/astral-sh/uv/issues/16813) — per-index exclude-newer override
- [astral-sh/uv#16846](https://github.com/astral-sh/uv/issues/16846) — per-package `= false` workaround
