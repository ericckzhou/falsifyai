"""Architectural assertion: ``CliInvocation`` is pure preservation-layer data (PR-35).

Mirrors the three existing ``_does_not_import_resolver`` tests for diff,
verify, and export. Scope is narrower than those, however:

Why narrower:
``cmd_run`` (where ``_capture_cli_invocation`` lives) legitimately imports
``verdict.resolver`` — it runs verdicts. An assertion that "importing
``cmd_run`` does not load the resolver" would fail by design.

What this enforces instead:
**Importing the ``CliInvocation`` data type alone must not transitively load
the resolver.** That guarantees the model lives in the preservation layer
and is reachable by read-only consumers (e.g., bundle README rendering) that
must not become resolver-coupled. If a future refactor moves CliInvocation
into a module that touches the resolver, this test fires.

This is the codified pattern from the PR-32 plan §10 (Tier-4 architectural
discipline): discipline encoded as system architecture, not as style guide.
"""

import sys


def test_cli_invocation_model_does_not_import_resolver() -> None:
    """Importing CliInvocation alone must not pull in falsifyai.verdict.resolver."""
    # Clear the relevant modules from sys.modules so the import is fresh.
    for mod_name in list(sys.modules):
        if mod_name.startswith("falsifyai.replay.models"):
            del sys.modules[mod_name]
        if mod_name == "falsifyai.verdict.resolver":
            del sys.modules[mod_name]

    # Import only the model type — not cmd_run, not the capture helper.
    from falsifyai.replay.models import CliInvocation  # noqa: F401

    assert "falsifyai.verdict.resolver" not in sys.modules, (
        "falsifyai.replay.models.CliInvocation must not transitively import "
        "falsifyai.verdict.resolver. CliInvocation is preservation-layer data "
        "that the bundle's README rendering reads without resolver coupling. "
        "If a refactor introduces this dependency, read-only consumer surfaces "
        "will pull the resolver too — violating the preservation discipline."
    )


def test_replay_models_module_does_not_import_resolver() -> None:
    """Broader assertion: nothing in falsifyai.replay.models imports the resolver.

    This was already implicit before PR-35 (the existing dataclasses don't
    touch verdict.resolver), but PR-35 adds a new field and a new dataclass.
    This test makes the constraint explicit so future field additions can't
    accidentally cross the layer boundary.
    """
    for mod_name in list(sys.modules):
        if mod_name.startswith("falsifyai.replay.models"):
            del sys.modules[mod_name]
        if mod_name == "falsifyai.verdict.resolver":
            del sys.modules[mod_name]

    import falsifyai.replay.models  # noqa: F401

    assert "falsifyai.verdict.resolver" not in sys.modules, (
        "falsifyai.replay.models must not transitively import "
        "falsifyai.verdict.resolver — the preservation layer must stay "
        "independent of the interpretation layer."
    )
