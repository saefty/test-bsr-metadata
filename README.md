# BSR + uv `exclude-newer` Incompatibility

Minimal reproduction of a dependency-resolution failure that occurs when using
[uv](https://docs.astral.sh/uv/)'s `exclude-newer` feature together with the
[Buf Schema Registry (BSR)](https://buf.build/docs/bsr/generated-sdks/python/)
as a Python package index.

---

## Root Cause

### How uv gets package timestamps

`exclude-newer` needs a publish timestamp for every candidate wheel.
uv requests timestamps via the **PEP 691 JSON Simple API**
(`Accept: application/vnd.pypi.simple.v1+json`). When a server supports it,
it returns JSON with an `upload-time` field per file (defined by PEP 700):

```json
{
  "files": [
    {
      "filename": "grpcio-1.80.0.tar.gz",
      "upload-time": "2015-03-30T23:24:33.390776Z",
      ...
    }
  ]
}
```

### What BSR returns

BSR claims PEP 503 (HTML) compatibility but **does not implement the PEP 691
JSON API**. When uv sends `Accept: application/vnd.pypi.simple.v1+json`, BSR
ignores the header and returns HTML:

```
$ curl -I -H "Accept: application/vnd.pypi.simple.v1+json" \
    https://buf.build/gen/python/simple/beta-googleapis-grpc-python/

content-type: text/html   ← should be application/vnd.pypi.simple.v1+json
```

The HTML response has no timestamp data. PEP 700 only defines `upload-time`
for the JSON format — there is no equivalent HTML attribute. Without
timestamps, uv conservatively rejects every BSR wheel.

---

## Reproducing the Error

**Prerequisites:** [uv](https://docs.astral.sh/uv/getting-started/installation/) ≥ 0.4

```bash
git clone https://github.com/saefty/test-bsr-metadata
cd test-bsr-metadata
uv sync
```

**Expected output:**

```
warning: beta_googleapis_grpc_python-1.80.0.1...whl is missing an upload date,
         but user provided: 2026-03-11T10:32:12.249238Z
  (... repeated for every BSR wheel ...)

× No solution found when resolving dependencies:
╰─▶ Because there are no versions of beta-googleapis-grpc-python and your
    project depends on beta-googleapis-grpc-python, we can conclude that
    your project's requirements are unsatisfiable.

    hint: `beta-googleapis-grpc-python` was filtered by `exclude-newer`
    to only include packages uploaded before 2026-03-11T10:32:12.249238Z.
    Consider using `exclude-newer-package` to override the cutoff for this
    package.
```

---

## What Does NOT Fix It

### `index-strategy = "unsafe-best-match"`

This controls which index wins when a package appears on multiple indices.
It has no effect on timestamp filtering. Verified: same error with or without it.

### `exclude-newer-package = { beta-googleapis-grpc-python = "2100-01-01" }`

Setting a per-package date override still rejects wheels with no timestamp,
regardless of the cutoff date. The hint in the error message is misleading
for this case.

### `exclude-newer-package = { beta-googleapis-grpc-python = false }` (uv ≥ 0.9.25)

Disabling the check for the named package resolves _that_ package, but BSR
packages pull transitive BSR deps (`beta-googleapis-protocolbuffers-python`,
etc.) that are also timestamp-free. uv must then check hundreds of wheel
files across every transitive dep before failing, making resolution hang for
minutes. You would have to enumerate every transitive BSR package manually —
fragile and impractical.

---

## Available Workarounds

### Option A — Per-index disable (uv ≥ 0.11.3, preview mode required)

PR [astral-sh/uv#18839](https://github.com/astral-sh/uv/pull/18839) (merged 2026-04-08)
adds `exclude-newer` as a per-index setting. This is the cleanest fix on the
uv side once it ships outside preview:

```toml
[tool.uv]
exclude-newer = "30d"
preview = true

[[tool.uv.index]]
url = "https://buf.build/gen/python"
name = "buf-bsr"
exclude-newer = false
```

### Option B — Remove `exclude-newer` globally

The only broadly working mitigation today is to omit `exclude-newer` from
projects that also depend on BSR packages.

**Security trade-off:** `exclude-newer` guards against supply-chain attacks
where a malicious version is backdated or future-dated to bypass a version
pin. Removing it globally disables that protection for PyPI packages too.

---

## The Proper Fix

BSR should implement the **PEP 691 JSON Simple API** and include
`upload-time` in its responses. This is a one-time addition that would make
BSR fully compatible with any tool using PEP 700 timestamps — not just uv.

Relevant specifications:
- [PEP 503](https://peps.python.org/pep-0503/) — Simple Repository API (HTML, what BSR implements today)
- [PEP 691](https://peps.python.org/pep-0691/) — JSON-based Simple API
- [PEP 700](https://peps.python.org/pep-0700/) — `upload-time` field in the JSON API

Related uv issues:
- [astral-sh/uv#12449](https://github.com/astral-sh/uv/issues/12449) — skip packages without publish date
- [astral-sh/uv#16813](https://github.com/astral-sh/uv/issues/16813) — per-index exclude-newer override
- [astral-sh/uv#16846](https://github.com/astral-sh/uv/issues/16846) — per-package `= false` workaround
