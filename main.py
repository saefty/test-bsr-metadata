"""
Minimal demo: BSR metadata issue with uv exclude-newer.

BSR (Buf Schema Registry) does not include 'upload-time' metadata in its
Simple Repository API responses. uv's `exclude-newer` feature relies on
this timestamp to filter packages. Without it, uv refuses to install BSR
packages when exclude-newer is configured.
"""
import grpc  # noqa: F401 - from PyPI, works fine

# In a real project you'd import generated stubs from BSR, e.g.:
# from buf_build.grpc.python import ...

print("If you see this, the workaround is in place.")
