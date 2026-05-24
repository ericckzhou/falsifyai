"""Portable evidence-bundle writer for stored ReplayArtifacts (PR-32).

A bundle is a deterministic zip file containing one ``ReplayArtifact``'s
full serialized form, an auto-generated README, and an optional source
spec YAML. It is the transport unit between archival systems — designed
to satisfy the EU AI Act Annex IV §2(g) shape (dated test logs with
identity anchors) without coupling to any specific compliance regime.

Public surface:

- :class:`BundleManifest` — the manifest payload (frozen dataclass)
- :class:`BundleFileEntry` — per-file SHA256 + size record
- :func:`write_bundle` — write a deterministic ``.fai.zip`` bundle
- :data:`BUNDLE_FORMAT_VERSION` / :data:`MANIFEST_SCHEMA_VERSION` /
  :data:`BUNDLE_TYPE` — schema discriminators

The bundle's ``bundle_id`` is a sha256-derived content address over the
canonical manifest (with the ``bundle_id`` field itself omitted). Two
exports of the same artifact with the same ``exported_at`` produce
byte-identical bundles and identical ids.
"""

from falsifyai.bundle.writer import (
    BUNDLE_FORMAT_VERSION,
    BUNDLE_TYPE,
    MANIFEST_SCHEMA_VERSION,
    BundleFileEntry,
    BundleManifest,
    write_bundle,
)

__all__ = [
    "BUNDLE_FORMAT_VERSION",
    "BUNDLE_TYPE",
    "MANIFEST_SCHEMA_VERSION",
    "BundleFileEntry",
    "BundleManifest",
    "write_bundle",
]
