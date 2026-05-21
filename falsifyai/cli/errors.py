"""CLI-layer exception hierarchy.

The CLI catches these and maps them to exit codes per
[plan.md section 16.1](../../plan.md). Code 3 (ERROR) is reserved for
infrastructure-class failures raised by the CLI layer *before* a verdict
exists — bad spec, missing API key, network unreachable, etc.

Verdict-derived exit codes (0, 1, 2, 4) come from
``falsifyai.cli.render.exit_code_for`` and never raise.
"""


class CLIError(Exception):
    """Base for all CLI-layer failures. Carries the intended exit code."""

    def __init__(self, message: str, *, exit_code: int = 3) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class SpecError(CLIError):
    """The spec file cannot be loaded or parsed."""


class ConfigError(CLIError):
    """A configuration / dependency / credential prerequisite is missing."""


class InfrastructureError(CLIError):
    """Network / model-call / store failure during a run."""
