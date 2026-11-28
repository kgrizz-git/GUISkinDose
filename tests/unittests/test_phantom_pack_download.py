"""Phantom-pack download transport, caps, cancellation, and trust checks."""

from __future__ import annotations

import inspect
import ssl
import threading
import time
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any, Self, cast

import pytest

from guiskindose.phantom_pack import PhantomPackError, manifest_sha256
from guiskindose.phantom_pack_download import (
    DOWNLOAD_CANCELLED,
    DOWNLOAD_INCOMPLETE,
    DOWNLOAD_OFFLINE,
    DOWNLOAD_REDIRECT_REFUSED,
    DOWNLOAD_TLS_FAILED,
    DOWNLOAD_TOO_LARGE,
    DownloadControl,
    DownloadProgress,
    PhantomPackDownloadCancelled,
    PhantomPackDownloadError,
    _download_from,
    _PinnedRedirectHandler,
    _tls_context,
    download_release_pack,
)
from guiskindose.phantom_pack_release import pack_release_url
from tests.unittests.phantom_pack_test_helpers import manifest_for_files, pack_zip_bytes, tiny_stl_body

_RELEASE_URL = "https://github.com/kgrizz-git/GUISkinDose/releases/download/v1.1.1/pack.zip"


class _Response:
    def __init__(self, body: bytes = b"", *, headers: dict[str, str] | None = None, status: int = 200) -> None:
        self._body = body
        self._position = 0
        self.headers = headers or {}
        self.status = status
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        if self.closed:
            raise ValueError("closed")
        end = len(self._body) if size < 0 else min(len(self._body), self._position + size)
        chunk = self._body[self._position : end]
        self._position = end
        return chunk

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


class _ScriptedTransport:
    def __init__(self, response: _Response | BaseException) -> None:
        self._response = response
        self.urls: list[str] = []

    def open(self, url: str, *, timeout: float) -> _Response:
        self.urls.append(url)
        if isinstance(self._response, BaseException):
            raise self._response
        return self._response


class _RedirectTransport:
    """Simulate GitHub's redirect to the asset CDN using the production policy."""

    def __init__(self, final_url: str, body: bytes) -> None:
        self.final_url = final_url
        self.body = body
        self.urls: list[str] = []

    def open(self, url: str, *, timeout: float) -> _Response:
        from guiskindose.phantom_pack_release import is_allowed_redirect_url

        self.urls.append(url)
        if url == _RELEASE_URL:
            assert is_allowed_redirect_url(self.final_url)
            return self.open(self.final_url, timeout=timeout)
        return _Response(body=self.body, headers={"Content-Length": str(len(self.body))}, status=200)


def _pack() -> tuple[bytes, str]:
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body}, app_version="1.1.1")
    pin = manifest_sha256(manifest)
    return pack_zip_bytes(manifest, {"senior_male": body}), pin


def _download(
    response: _Response | BaseException,
    *,
    tmp_path: Path,
    pin: str | None = None,
    control: DownloadControl | None = None,
    progress: DownloadProgress | None = None,
):
    _raw, expected = _pack()
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    shipped.mkdir()
    return _download_from(
        _RELEASE_URL,
        transport=_ScriptedTransport(response),
        expected_manifest_sha256=pin if pin is not None else expected,
        app_version="1.1.1",
        user_library_dir=library,
        shipped_dir=shipped,
        control=control or DownloadControl(),
        progress=progress or DownloadProgress(),
    ), library


def test_public_api_has_no_url_or_insecure_knobs() -> None:
    parameters = inspect.signature(download_release_pack).parameters
    for forbidden in ("url", "opener", "transport", "allow_insecure_loopback", "cacert"):
        assert forbidden not in parameters
    forbidden_call = {
        "url": _RELEASE_URL,
        "expected_manifest_sha256": "0" * 64,
        "app_version": "1.1.1",
        "user_library_dir": Path(),
        "shipped_dir": Path(),
        "control": DownloadControl(),
        "progress": DownloadProgress(),
    }
    untyped_download = cast(Any, download_release_pack)
    with pytest.raises(TypeError):
        untyped_download(**forbidden_call)


def test_happy_path_installs_into_temp_library(tmp_path: Path) -> None:
    raw, _pin = _pack()
    result, library = _download(_Response(raw, headers={"Content-Length": str(len(raw))}), tmp_path=tmp_path)
    assert result.installed == 1
    assert (library / "senior_male.stl").read_bytes() == tiny_stl_body()


def test_404_uses_not_published_sentence(tmp_path: Path) -> None:
    error = urllib.error.HTTPError(_RELEASE_URL, 404, "Not Found", Message(), None)
    with pytest.raises(PhantomPackDownloadError, match="No phantom pack is published"):
        _download(error, tmp_path=tmp_path)


def test_offline_uses_fixed_sentence(tmp_path: Path) -> None:
    error = urllib.error.URLError(OSError("connection refused"))
    with pytest.raises(PhantomPackDownloadError) as info:
        _download(error, tmp_path=tmp_path)
    assert str(info.value) == DOWNLOAD_OFFLINE
    assert not (tmp_path / "library").exists()


def test_tls_failure_uses_fixed_sentence(tmp_path: Path) -> None:
    tls_error = ssl.SSLCertVerificationError("bad certificate")
    with pytest.raises(PhantomPackDownloadError) as info:
        _download(tls_error, tmp_path=tmp_path)
    assert str(info.value) == DOWNLOAD_TLS_FAILED


def test_tls_context_is_always_verified() -> None:
    context = _tls_context()
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2


def test_declared_oversize_is_refused_before_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("guiskindose.phantom_pack_download.MAX_COMPRESSED_PACK_BYTES", 64)
    response = _Response(b"x", headers={"Content-Length": "65"})
    with pytest.raises(PhantomPackDownloadError) as info:
        _download(response, tmp_path=tmp_path)
    assert str(info.value) == DOWNLOAD_TOO_LARGE


def test_actual_oversize_is_stopped_mid_stream(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("guiskindose.phantom_pack_download.MAX_COMPRESSED_PACK_BYTES", 64)
    response = _Response(b"x" * 200, headers={"Content-Length": "10"})
    with pytest.raises(PhantomPackDownloadError) as info:
        _download(response, tmp_path=tmp_path)
    assert str(info.value) == DOWNLOAD_TOO_LARGE


def test_truncated_body_uses_incomplete_sentence(tmp_path: Path) -> None:
    response = _Response(b"short", headers={"Content-Length": "100"})
    with pytest.raises(PhantomPackDownloadError) as info:
        _download(response, tmp_path=tmp_path)
    assert str(info.value) == DOWNLOAD_INCOMPLETE


def test_pin_mismatch_is_rejected(tmp_path: Path) -> None:
    raw, _pin = _pack()
    response = _Response(raw, headers={"Content-Length": str(len(raw))})
    with pytest.raises(PhantomPackError, match="not recognized"):
        _download(response, tmp_path=tmp_path, pin="0" * 64)
    assert not (tmp_path / "library" / "senior_male.stl").exists()


def test_tampered_member_is_rejected(tmp_path: Path) -> None:
    body = tiny_stl_body()
    manifest = manifest_for_files({"senior_male": body}, app_version="1.1.1")
    pin = manifest_sha256(manifest)
    raw = pack_zip_bytes(manifest, {"senior_male": body + b"#"})
    response = _Response(raw, headers={"Content-Length": str(len(raw))})
    with pytest.raises(PhantomPackError, match=r"hash|manifest|valid"):
        _download(response, tmp_path=tmp_path, pin=pin)


def test_cancel_closes_response_and_returns_promptly(tmp_path: Path) -> None:
    started = threading.Event()
    released = threading.Event()
    raw, _pin = _pack()

    class _BlockingResponse(_Response):
        def read(self, size: int = -1) -> bytes:
            started.set()
            released.wait(5)
            if self.closed:
                raise ValueError("closed")
            return raw

        def close(self) -> None:
            self.closed = True
            released.set()

    control = DownloadControl()
    response = _BlockingResponse(headers={"Content-Length": str(len(raw))})
    errors: list[BaseException] = []

    def _run() -> None:
        try:
            _download(response, tmp_path=tmp_path, control=control)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=_run)
    thread.start()
    assert started.wait(2)
    began = time.monotonic()
    control.cancel()
    thread.join(2)
    assert not thread.is_alive()
    assert time.monotonic() - began < 1.5
    assert errors
    assert isinstance(errors[0], PhantomPackDownloadCancelled)
    assert str(errors[0]) == DOWNLOAD_CANCELLED
    assert not (tmp_path / "library").exists()


def test_redirect_handler_refuses_other_hosts() -> None:
    import urllib.request

    handler = _PinnedRedirectHandler()
    req = urllib.request.Request(_RELEASE_URL)
    with pytest.raises(PhantomPackDownloadError) as info:
        handler.redirect_request(req, None, 302, "Found", {}, "https://evil.example/pack.zip")
    assert str(info.value) == DOWNLOAD_REDIRECT_REFUSED


def test_redirect_handler_keeps_the_signed_query() -> None:
    import urllib.request

    handler = _PinnedRedirectHandler()
    target = "https://release-assets.githubusercontent.com/pack.zip?X-Amz-Signature=abc"
    result = handler.redirect_request(
        urllib.request.Request(_RELEASE_URL), None, 302, "Found", {}, target
    )
    assert result is not None
    assert result.full_url == target


def test_signed_redirect_query_is_preserved_and_not_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    raw, pin = _pack()
    signed = "https://release-assets.githubusercontent.com/pack.zip?X-Amz-Signature=SECRETVALUE"
    transport = _RedirectTransport(signed, raw)
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    shipped.mkdir()
    # The fake transport follows its own 302; _download_from receives the final response.
    transport.open = _RedirectTransport.open.__get__(transport, _RedirectTransport)  # type: ignore[method-assign]
    result = _download_from(
        _RELEASE_URL,
        transport=transport,
        expected_manifest_sha256=pin,
        app_version="1.1.1",
        user_library_dir=library,
        shipped_dir=shipped,
        control=DownloadControl(),
        progress=DownloadProgress(),
    )
    assert result.installed == 1
    assert any("X-Amz-Signature=SECRETVALUE" in url for url in transport.urls)
    assert "SECRETVALUE" not in caplog.text
    assert "X-Amz-Signature" not in caplog.text


def test_release_url_is_the_only_production_start() -> None:
    assert pack_release_url("1.1.1") is not None
    assert pack_release_url("0.0.0+unknown") is None


def test_download_size_cap_matches_install_cap() -> None:
    import guiskindose.phantom_pack_download as download
    import guiskindose.phantom_pack_install as install

    assert download.MAX_COMPRESSED_PACK_BYTES == install.MAX_COMPRESSED_PACK_BYTES


def test_cancel_after_body_before_install_leaves_library_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from guiskindose import phantom_pack_download as download

    raw, pin = _pack()
    shipped = tmp_path / "shipped"
    library = tmp_path / "library"
    shipped.mkdir()
    control = DownloadControl()
    original = download._read_body

    def _read_then_cancel(response, spool, *, control, progress):
        original(response, spool, control=control, progress=progress)
        control.cancel()

    installed: list[object] = []
    response = _Response(raw, headers={"Content-Length": str(len(raw))})
    transport = _ScriptedTransport(response)
    progress = DownloadProgress()
    monkeypatch.setattr(download, "_read_body", _read_then_cancel)
    monkeypatch.setattr(download, "install_phantom_pack", lambda *args, **kwargs: installed.append((args, kwargs)))
    with pytest.raises(PhantomPackDownloadCancelled) as info:
        download._download_from(
            _RELEASE_URL,
            transport=transport,
            expected_manifest_sha256=pin,
            app_version="1.1.1",
            user_library_dir=library,
            shipped_dir=shipped,
            control=control,
            progress=progress,
        )
    assert str(info.value) == DOWNLOAD_CANCELLED
    assert installed == []
    assert not library.exists()


def test_malformed_content_length_still_hits_the_streaming_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("guiskindose.phantom_pack_download.MAX_COMPRESSED_PACK_BYTES", 64)
    response = _Response(b"x" * 200, headers={"Content-Length": "not-a-number"})
    with pytest.raises(PhantomPackDownloadError) as info:
        _download(response, tmp_path=tmp_path)
    assert str(info.value) == DOWNLOAD_TOO_LARGE
