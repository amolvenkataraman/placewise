"""Fetching URLs with the standard library: size limits, a generic User-Agent, and only the schemes
the store expects (https, http, file)."""

import functools
import hashlib
import urllib.parse

import placewise
from placewise.constants import store as const

from .errors import DownloadError

# urllib.request (with http.client and email) costs ~20 ms to import and only downloads need it, so
# lookups that read installed packs never load it


@functools.cache
def _opener():
    import urllib.request

    class _SafeRedirects(urllib.request.HTTPRedirectHandler):
        # urllib would follow a redirect to ftp://; a server should only ever bounce us to another web URL
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if urllib.parse.urlsplit(newurl).scheme not in ("http", "https"):
                raise DownloadError(f"{req.full_url} redirected to a non-web URL {newurl}")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return urllib.request.build_opener(_SafeRedirects)


def check_scheme(url):
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if scheme not in const.URL_SCHEMES:
        raise DownloadError(f"unsupported URL scheme {scheme!r} in {url}; use {', '.join(const.URL_SCHEMES)}")


def _open(url):
    import urllib.error
    import urllib.request

    check_scheme(url)
    request = urllib.request.Request(
        url, headers={"User-Agent": const.USER_AGENT.format(version=placewise.__version__)}
    )
    try:
        return _opener().open(request, timeout=const.HTTP_TIMEOUT_S)
    except urllib.error.HTTPError as e:
        raise DownloadError(f"HTTP {e.code} {e.reason}") from None
    except urllib.error.URLError as e:
        raise DownloadError(str(e.reason)) from None
    except (OSError, ValueError) as e:  # timeouts, resets, malformed URLs
        raise DownloadError(str(e) or type(e).__name__) from None


def _check_length(response, limit):
    length = response.headers.get("Content-Length")
    if length and length.isdigit() and int(length) > limit:
        raise DownloadError(f"{response.geturl()} is {length} bytes, larger than the {limit}-byte limit")


def fetch_bytes(url, limit):
    """The whole body, refusing anything over `limit` bytes."""
    with _open(url) as response:
        _check_length(response, limit)
        try:
            data = response.read(limit + 1)
        except OSError as e:
            raise DownloadError(str(e) or type(e).__name__) from None
    if len(data) > limit:
        raise DownloadError(f"{url} is larger than the {limit}-byte limit")
    return data


def fetch_file(url, dest, *, expected_size, limit, progress=None, heartbeat=None):
    """Stream `url` into a new file `dest`, stopping past `limit` bytes. Returns the SHA-256 hex digest.

    `progress(done_bytes, expected_size)` is called as data arrives; `heartbeat()` too, so a caller
    holding a lock can keep it fresh during a long download.
    """
    digest = hashlib.sha256()
    done = 0
    with _open(url) as response, open(dest, "xb") as out:
        _check_length(response, limit)
        if progress:
            progress(0, expected_size)
        while True:
            try:
                chunk = response.read(const.CHUNK_BYTES)
            except OSError as e:
                raise DownloadError(str(e) or type(e).__name__) from None
            if not chunk:
                break
            done += len(chunk)
            if done > limit:
                raise DownloadError(
                    f"{url} is larger than the {expected_size} bytes expected; stopped at {done}"
                )
            digest.update(chunk)
            out.write(chunk)
            if progress:
                progress(done, expected_size)
            if heartbeat:
                heartbeat()
    return digest.hexdigest()


def index_location(url):
    """A mirror or index URL naming a directory gets index.json appended; one naming a file is kept."""
    if urllib.parse.urlsplit(url).path.endswith(".json"):
        return url
    return url.rstrip("/") + "/" + const.INDEX_FILENAME


def resolve(base, url):
    """Relative pack URLs resolve against the index's own URL, so a mirror is a copy of the directory."""
    return urllib.parse.urljoin(base, url)
