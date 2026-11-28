"""Download the phantom pack published for this application release.

The public entry point takes no URL and no transport override. The release URL
is derived from the running version by :mod:`guiskindose.phantom_pack_release`,
TLS is always verified, and redirects are restricted to GitHub's release hosts.
The downloaded stream is handed to :func:`phantom_pack_install.install_phantom_pack`,
so the manifest pin and per-member hashes are the same checks a local zip gets.
"""

from __future__ import annotations

import http.client
import logging
import ssl
import tempfile
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any, Protocol

import certifi

from guiskindose.phantom_pack import PhantomPackError
from guiskindose.phantom_pack_install import (
    MAX_COMPRESSED_PACK_BYTES,
    InstallResult,
    install_phantom_pack,
)
from guiskindose.phantom_pack_release import (
    is_allowed_pack_url,
    is_allowed_redirect_url,
    pack_release_url,
)
from guiskindose.privacy import safe_error_event

_LOG = logging.getLogger(__name__)

_OPERATION = "phantom_pack_download"
_SOCKET_TIMEOUT_SECONDS = 5.0
_READ_CHUNK_BYTES = 64 * 1024
_SPOOL_MAX_BYTES = 8 * 1024 * 1024
_MAX_REDIRECTS = 5

DOWNLOAD_UNAVAILABLE = "This build has no downloadable phantom pack. Install a pack zip instead."
DOWNLOAD_NOT_PUBLISHED = (
    "No phantom pack is published for this GUISkinDose version. "
    "Install a pack zip, or use the GUISkinDose Full download."
)
DOWNLOAD_OFFLINE = (
    "Could not reach the GUISkinDose release server. Installed meshes are unchanged."
)
DOWNLOAD_TLS_FAILED = (
    "A secure connection to the GUISkinDose release server could not be established."
)
DOWNLOAD_REDIRECT_REFUSED = (
    "The download was redirected to an untrusted host and was stopped."
)
DOWNLOAD_TOO_LARGE = (
    "The phantom pack download exceeded the size limit and was stopped."
)
DOWNLOAD_INCOMPLETE = (
    "The phantom pack download did not finish. Installed meshes are unchanged."
)
DOWNLOAD_CANCELLED = "Download cancelled. Installed meshes are unchanged."
DOWNLOAD_FAILED = "Phantom pack download failed. Installed meshes are unchanged."


class PhantomPackDownloadError(PhantomPackError):
    """A download failure with a fixed, value-free user sentence."""


class PhantomPackDownloadCancelled(PhantomPackDownloadError):
    """The user cancelled the download before install."""


class DownloadProgress:
    """Thread-safe byte progress written by the worker and read by the UI."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._received = 0
        self._total: int | None = None
        self._phase = "downloading"

    def update(self, *, received: int | None = None, total: int | None = None, phase: str | None = None) -> None:
        with self._lock:
            if received is not None:
                self._received = received
            if total is not None:
                self._total = total
            if phase is not None:
                self._phase = phase

    def snapshot(self) -> tuple[int, int | None, str]:
        """Return ``(received, total, phase)``."""
        with self._lock:
            return self._received, self._total, self._phase


class DownloadControl:
    """Cancel flag plus the response handle a cancel may close to unblock a read."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._closer: Callable[[], None] | None = None

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def bind_response(self, closer: Callable[[], None] | None) -> None:
        """Register the response's close callable; close immediately if already cancelled."""
        with self._lock:
            self._closer = closer
            cancelled = self._event.is_set()
        if cancelled and closer is not None:
            _close_quietly(closer)

    def cancel(self) -> None:
        """Set the flag and close the live response, if any."""
        self._event.set()
        with self._lock:
            closer = self._closer
        if closer is not None:
            _close_quietly(closer)


def _close_quietly(closer: Callable[[], None]) -> None:
    try:
        closer()
    except Exception:
        return


class _Transport(Protocol):
    """One HTTP request. Tests supply their own implementation."""

    def open(self, url: str, *, timeout: float) -> Any: ...


class _PinnedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only when its target is HTTPS on an allowed GitHub host."""

    max_redirections = _MAX_REDIRECTS

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        if not is_allowed_redirect_url(newurl):
            raise PhantomPackDownloadError(DOWNLOAD_REDIRECT_REFUSED)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _tls_context() -> ssl.SSLContext:
    """Return the shared verified context; never disable verification."""
    context = ssl.create_default_context(cafile=certifi.where())
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


class _UrllibTransport:
    """Production transport: verified HTTPS, environment proxies, pinned redirects."""

    def __init__(self, *, app_version: str) -> None:
        self._app_version = app_version
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(),
            urllib.request.HTTPSHandler(context=_tls_context()),
            _PinnedRedirectHandler(),
        )

    def open(self, url: str, *, timeout: float) -> Any:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/zip",
                "Connection": "close",
                "User-Agent": f"GUISkinDose/{self._app_version}",
            },
        )
        return self._opener.open(request, timeout=timeout)


def _content_length(headers: Any) -> int | None:
    try:
        raw = headers.get("Content-Length")
        value = int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        # A malformed header is ignored; the streaming cap in _read_body still applies.
        return None
    return value if value > 0 else None


def _transport_error_message(exc: BaseException) -> str:
    """Map one transport exception to a fixed user sentence."""
    if isinstance(exc, urllib.error.HTTPError):
        return DOWNLOAD_NOT_PUBLISHED if exc.code == 404 else DOWNLOAD_FAILED
    if isinstance(exc, (ssl.SSLError, ssl.CertificateError)):
        return DOWNLOAD_TLS_FAILED
    if isinstance(exc, urllib.error.URLError):
        if isinstance(exc.reason, (ssl.SSLError, ssl.CertificateError)):
            return DOWNLOAD_TLS_FAILED
        return DOWNLOAD_OFFLINE
    if isinstance(exc, (TimeoutError, OSError)):
        return DOWNLOAD_OFFLINE
    return DOWNLOAD_FAILED


def _open_response(transport: _Transport, url: str, control: DownloadControl) -> Any:
    """Open *url* and map transport failures to fixed sentences."""
    try:
        return transport.open(url, timeout=_SOCKET_TIMEOUT_SECONDS)
    except PhantomPackDownloadError:
        raise
    except Exception as exc:
        safe_error_event(_LOG, _OPERATION, exc)
        if control.cancelled:
            raise PhantomPackDownloadCancelled(DOWNLOAD_CANCELLED) from None
        raise PhantomPackDownloadError(_transport_error_message(exc)) from None


def _read_body(response: Any, *, control: DownloadControl, progress: DownloadProgress) -> IO[bytes]:
    """Stream the response into a prefixed spool under the compressed-size cap."""
    total = _content_length(getattr(response, "headers", {}))
    if total is not None and total > MAX_COMPRESSED_PACK_BYTES:
        raise PhantomPackDownloadError(DOWNLOAD_TOO_LARGE)
    progress.update(total=total)
    spool = tempfile.SpooledTemporaryFile(  # noqa: SIM115 - returned to the installer, closed by the worker
        max_size=_SPOOL_MAX_BYTES,
        prefix="guiskindose-pack-",
    )
    control.bind_response(response.close)
    received = 0
    try:
        while True:
            if control.cancelled:
                raise PhantomPackDownloadCancelled(DOWNLOAD_CANCELLED)
            try:
                chunk = response.read(_READ_CHUNK_BYTES)
            except (OSError, ValueError, http.client.HTTPException) as exc:
                if control.cancelled:
                    raise PhantomPackDownloadCancelled(DOWNLOAD_CANCELLED) from exc
                safe_error_event(_LOG, _OPERATION, exc)
                raise PhantomPackDownloadError(DOWNLOAD_INCOMPLETE) from None
            if not chunk:
                break
            received += len(chunk)
            if received > MAX_COMPRESSED_PACK_BYTES:
                raise PhantomPackDownloadError(DOWNLOAD_TOO_LARGE)
            spool.write(chunk)
            progress.update(received=received)
        if total is not None and received != total:
            raise PhantomPackDownloadError(DOWNLOAD_INCOMPLETE)
    except BaseException:
        spool.close()
        raise
    finally:
        control.bind_response(None)
    spool.seek(0)
    return spool


def _download_from(
    url: str,
    *,
    transport: _Transport,
    expected_manifest_sha256: str,
    app_version: str,
    user_library_dir: Path,
    shipped_dir: Path,
    control: DownloadControl,
    progress: DownloadProgress,
) -> InstallResult:
    """Private transport seam used by tests; production callers use the public function."""
    if not is_allowed_pack_url(url):
        raise PhantomPackDownloadError(DOWNLOAD_UNAVAILABLE)
    response = _open_response(transport, url, control)
    spool: IO[bytes] | None = None
    try:
        with response:
            spool = _read_body(response, control=control, progress=progress)
        # A cancel that lands after the last chunk but before publish must not install.
        if control.cancelled:
            raise PhantomPackDownloadCancelled(DOWNLOAD_CANCELLED)
        progress.update(phase="installing")
        return install_phantom_pack(
            spool,
            user_library_dir=user_library_dir,
            shipped_dir=shipped_dir,
            expected_manifest_sha256=expected_manifest_sha256,
            app_version=app_version,
        )
    finally:
        if spool is not None:
            spool.close()


def download_release_pack(
    *,
    expected_manifest_sha256: str,
    app_version: str,
    user_library_dir: Path,
    shipped_dir: Path,
    control: DownloadControl,
    progress: DownloadProgress,
) -> InstallResult:
    """Download this build's pinned phantom pack and install it.

    The public API deliberately accepts no URL, opener, transport, or insecure
    flag. Tests use the private ``_download_from`` seam.
    """
    url = pack_release_url(app_version)
    if url is None:
        raise PhantomPackDownloadError(DOWNLOAD_UNAVAILABLE)
    return _download_from(
        url,
        transport=_UrllibTransport(app_version=app_version),
        expected_manifest_sha256=expected_manifest_sha256,
        app_version=app_version,
        user_library_dir=user_library_dir,
        shipped_dir=shipped_dir,
        control=control,
        progress=progress,
    )
