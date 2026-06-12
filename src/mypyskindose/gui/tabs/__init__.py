"""Per-tab page builders extracted from app.index() (refactor plan Phase 3.3).

Each module exposes ``build(ctx: PageContext) -> None`` which renders one
``ui.tab_panel`` (and registers that tab's timers/handlers). ``app.index()``
calls them inside its ``ui.tab_panels`` block.
"""
