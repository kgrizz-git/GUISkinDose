"""render_bytes() should translate a missing optional backend into an actionable error."""

from __future__ import annotations

import builtins
import sys

import pytest

from guiskindose.export import MissingExportDependencyError
from guiskindose.export.writers import render_bytes


def _block_import(monkeypatch: pytest.MonkeyPatch, blocked: str, writer_submodule: str) -> None:
    """Make ``import <blocked>`` raise, and force the writer submodule to re-import."""
    # Drop any cached writer + backend so the lazy import re-executes and fails.
    for name in list(sys.modules):
        if name == blocked or name.startswith(f"{blocked}."):
            monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.delitem(sys.modules, f"guiskindose.export.writers.{writer_submodule}", raising=False)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        top = name.split(".")[0]
        if top == blocked:
            raise ModuleNotFoundError(f"No module named {blocked!r}", name=top)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_pdf_missing_reportlab_raises_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_import(monkeypatch, "reportlab", "pdf")
    with pytest.raises(MissingExportDependencyError) as excinfo:
        render_bytes(object(), "pdf")  # type: ignore[arg-type]
    exc = excinfo.value
    assert exc.format == "pdf"
    assert exc.package == "reportlab"
    assert "guiskindose[export]" in exc.install_hint
    assert "reportlab" in str(exc)


def test_docx_missing_python_docx_raises_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_import(monkeypatch, "docx", "docx")
    with pytest.raises(MissingExportDependencyError) as excinfo:
        render_bytes(object(), "docx")  # type: ignore[arg-type]
    exc = excinfo.value
    assert exc.package == "docx"
    # Install hint uses the pip name, which differs from the import name.
    assert "python-docx" in exc.install_hint
