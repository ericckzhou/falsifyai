"""``falsifyai`` command-line interface.

The console script entry point ``falsifyai = "falsifyai.cli.main:main"`` is
wired in ``pyproject.toml``. Import the submodule directly
(``from falsifyai.cli.main import main``) — no re-export here, because doing
so would shadow the ``falsifyai.cli.main`` submodule with its ``main``
function and break ``import falsifyai.cli.main``.
"""
