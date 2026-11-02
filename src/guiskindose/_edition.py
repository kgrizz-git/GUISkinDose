"""Build edition of this copy of GUISkinDose.

The committed value is ``"full"``, and the pip wheel ships it unchanged. The portable
freeze (``packaging/portable/guiskindose.spec``) rewrites this file in a gitignored
staging copy only, to ``"light"`` or ``"full"``. Read it through
``guiskindose.edition.current_edition()``. No environment variable overrides it.
"""

EDITION = "full"
