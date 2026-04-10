# BSR + uv `exclude-newer` Incompatibility

Minimal reproduction of a dependency-resolution failure that occurs when using
[uv](https://docs.astral.sh/uv/)'s `exclude-newer` feature together with the
[Buf Schema Registry (BSR)](https://buf.build/docs/bsr/generated-sdks/python/)
as a Python package index.

---

## The Problem

uv's `exclude-newer` setting filters packages by their **upload timestamp**.
It reads this from the `data-upload-time` attribute that PyPI includes on every
wheel link in its [Simple Repository API](https://peps.python.org/pep-0700/)
responses, for example:

```html
<!-- PyPI — has the attribute -->
<a href="...grpcio-1.80.0.tar.gz"
   data-upload-time="2025-03-05T18:11:12.158875Z"
   ...>grpcio-1.80.0.tar.gz</a>
```

BSR's Simple API **does not include this attribute**:

```html
<!-- BSR — attribute is absent -->
<a href="...beta_googleapis_grpc_python-1.80.0.1...whl"
   data-requires-python=">=3.8"
   data-core-metadata="...whl.metadata"
   ...>beta_googleapis_grpc_python-1.80.0.1...whl</a>
```

When `exclude-newer` is configured and a package has no timestamp, uv
conservatively treats every version as unresolvable, producing:

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

## Reproducing

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) ≥ 0.4

### Steps

```bash
git clone https://github.com/saefty/test-bsr-metadata
cd test-bsr-metadata
```

**Scenario 1 — Failure**

Enable `exclude-newer` in `pyproject.toml`:

```toml
[tool.uv]
exclude-newer = "30d"   # uncomment this line
```

Then run:

```bash
uv sync
```

Expected: resolution fails with the "missing an upload date" warnings above.

**Scenario 2 — Workaround**

Comment `exclude-newer` back out (current default in this repo) and re-run:

```bash
uv sync   # succeeds
```

---

## What Does NOT Fix It

### `index-strategy = "unsafe-best-match"`

This option controls which index takes priority when a package exists on
**multiple indices**. It has no effect on the timestamp-filtering logic and does
not resolve the failure.

### `exclude-newer-package = { beta-googleapis-grpc-python = "2100-01-01" }`

uv's own error hint suggests this, but it does not help. When a package wheel
has **no timestamp at all**, uv rejects it regardless of what per-package cutoff
date is configured. The hint is misleading for this case.

---

## The Real Workaround (and Its Trade-off)

The only currently working mitigation is to **remove `exclude-newer` entirely**
(or not use it in projects that also depend on BSR packages).

**Security implication:** `exclude-newer` is a supply-chain guard. It prevents
uv from installing a package whose index entry was backdated or future-dated to
slip past a version pin. Removing it globally disables that protection for all
packages in the project, including PyPI ones where it is meaningful.

---

## Why This Matters

BSR-generated Python SDKs are the recommended way to consume Protobuf/gRPC
definitions from buf.build. Teams using uv with `exclude-newer` as a
reproducibility or security control cannot use BSR as a package index without
either disabling that control or splitting BSR dependencies into a separate
project.

---

## The Right Fix

Buf should add `data-upload-time` to BSR's Simple API responses, as specified
by [PEP 700](https://peps.python.org/pep-0700/). This would allow uv (and any
other PEP 700-compliant resolver) to apply timestamp-based filtering correctly.

Related:
- [uv docs — `exclude-newer`](https://docs.astral.sh/uv/reference/settings/#exclude-newer)
- [PEP 700 — `data-upload-time`](https://peps.python.org/pep-0700/)
- [BSR Python SDK docs](https://buf.build/docs/bsr/generated-sdks/python/)
