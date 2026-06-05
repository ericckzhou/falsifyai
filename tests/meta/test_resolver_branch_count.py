"""Structural guardrail: the verdict resolver's decision chain stays bounded.

This is anti-entropy infrastructure for the project's load-bearing rule
(``.claude/CLAUDE.md``): *the verdict resolver is the epistemic authority of
the framework; its priority chain must stay compressible and predictable.*

The mechanism: count the ``return Verdict.X`` statements in
``_decide_verdict``. That count is the number of distinct verdict *classes* the
resolver can emit. It is allowed to change only when a new verdict class is
deliberately wired in (e.g. PR-D adds ``INVALID_EVAL`` via the meta-oracle).
It must **never** grow because a new *oracle* was added: oracles pre-arbitrate
into an ``OracleVerdict`` and the resolver consumes a single, already-resolved
contribution. If adding an oracle makes this test fail, the oracle is leaking
its own branch into the resolver — route it through arbitration instead.

When the count legitimately changes, update ``_EXPECTED_VERDICT_RETURNS`` in the
same commit that adds the verdict class, and say why in the commit message.
"""

import ast
import inspect

from falsifyai.verdict import resolver

# Locked baseline. Changes ONLY when a new verdict *class* is wired in, never
# when an oracle is added (oracles pre-arbitrate; the resolver consumes their
# verdicts by precedence).
#
# History:
#   4 -- INSUFFICIENT, CONSISTENTLY_WRONG, FRAGILE, STABLE (PR-#11 resolver, PR-C)
#   5 -- + INVALID_EVAL via the MetaOracle (PR-D). One-time growth: INVALID_EVAL
#        is a genuinely new verdict class with a new top-priority branch. The
#        MetaOracle is its sole source; future oracles emitting *existing*
#        classes must route through the relevant branch, not add a new one.
_EXPECTED_VERDICT_RETURNS = 5


def _decide_verdict_ast() -> ast.FunctionDef:
    source = inspect.getsource(resolver._decide_verdict)
    module = ast.parse(source)
    func = module.body[0]
    assert isinstance(func, ast.FunctionDef)
    return func


def _count_verdict_returns(func: ast.FunctionDef) -> int:
    """Count ``return Verdict.<NAME>`` statements within ``func``."""
    count = 0
    for node in ast.walk(func):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Attribute):
            value = node.value
            if isinstance(value.value, ast.Name) and value.value.id == "Verdict":
                count += 1
    return count


def test_decide_verdict_branch_count_is_locked() -> None:
    func = _decide_verdict_ast()
    actual = _count_verdict_returns(func)
    assert actual == _EXPECTED_VERDICT_RETURNS, (
        f"_decide_verdict now emits {actual} verdict classes, expected "
        f"{_EXPECTED_VERDICT_RETURNS}. If you added an ORACLE, route it through "
        f"OracleVerdict arbitration instead of a new resolver branch. If you "
        f"deliberately added a VERDICT CLASS, bump _EXPECTED_VERDICT_RETURNS and "
        f"explain why in the commit."
    )
