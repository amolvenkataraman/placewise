"""packbuild.zipranges: some members of a remote zip, by HTTP range requests (no network: a fake
server answers the ranges from bytes in memory)."""

import io
import json
import os
import urllib.error
import zipfile

import pytest

from packbuild import zipranges

URL = "https://example.org/download/xyz_admin_boundaries.shp.zip"
FINAL = "https://s3.example.org/signed/xyz_admin_boundaries.shp.zip?sig=1"


def make_zip(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buffer.getvalue()


class Server:
    """Serves byte ranges of one archive; the first URL redirects to FINAL."""

    def __init__(self, data, expire_after=None):
        self.data, self.calls, self.expire_after = data, [], expire_after

    def __call__(self, url, start, end):
        self.calls.append((url, start, end))
        if url == FINAL and self.expire_after is not None and len(self.calls) > self.expire_after:
            self.expire_after = None  # the next resolve gives a fresh URL that works
            raise urllib.error.HTTPError(url, 403, "Request has expired", {}, None)
        assert url in (URL, FINAL)
        return self.data[start : end + 1], len(self.data), FINAL

    def served(self):
        return sum(end - start + 1 for _, start, end in self.calls)


@pytest.fixture
def archive():
    big = os.urandom(3_000_000)  # incompressible: the member we never ask for
    return make_zip({"xyz_admin1.shp": b"shapes" * 1000, "xyz_admin1.dbf": b"table", "xyz_admin4.shp": big})


def test_only_the_asked_members_are_downloaded(tmp_path, archive, monkeypatch):
    monkeypatch.setattr(zipranges, "BLOCK", 64 * 1024)
    server = Server(archive)
    folder = zipranges.fetch_members(URL, ["xyz_admin1.shp", "xyz_admin1.dbf"], tmp_path, ranged=server)
    assert folder == tmp_path / "xyz_admin_boundaries.shp"
    assert (folder / "xyz_admin1.shp").read_bytes() == b"shapes" * 1000
    assert (folder / "xyz_admin1.dbf").read_bytes() == b"table"
    assert not (folder / "xyz_admin4.shp").exists()
    assert server.served() < len(archive) / 10  # the 3 MB member was never read
    meta = json.loads((tmp_path / "xyz_admin_boundaries.shp.members.json").read_text())
    assert meta["url"] == URL and meta["archive_size"] == len(archive)
    assert set(meta["members"]) == {"xyz_admin1.shp", "xyz_admin1.dbf"}
    assert (
        meta["members"]["xyz_admin1.dbf"]["size"] == 5
        and len(meta["members"]["xyz_admin1.dbf"]["sha256"]) == 64
    )


def test_cached_members_are_not_fetched_again_and_new_ones_are_added(tmp_path, archive):
    zipranges.fetch_members(URL, ["xyz_admin1.dbf"], tmp_path, ranged=Server(archive))
    again = Server(archive)
    zipranges.fetch_members(URL, ["xyz_admin1.dbf"], tmp_path, ranged=again)
    assert again.calls == []
    zipranges.fetch_members(URL, ["xyz_admin1.shp"], tmp_path, ranged=again)
    meta = json.loads((tmp_path / "xyz_admin_boundaries.shp.members.json").read_text())
    assert set(meta["members"]) == {"xyz_admin1.shp", "xyz_admin1.dbf"}


def test_a_whole_cached_zip_is_unzipped_instead(tmp_path, archive):
    (tmp_path / "xyz_admin_boundaries.shp.zip").write_bytes(archive)
    (tmp_path / "xyz_admin_boundaries.shp.zip.json").write_text("{}")
    server = Server(archive)
    folder = zipranges.fetch_members(URL, ["xyz_admin1.dbf"], tmp_path, ranged=server)
    assert server.calls == [] and (folder / "xyz_admin4.shp").exists()


def test_a_missing_member_names_what_the_zip_has(tmp_path, archive):
    with pytest.raises(KeyError, match=r"xyz_admin9\.shp.*xyz_admin1\.dbf"):
        zipranges.fetch_members(URL, ["xyz_admin9.shp"], tmp_path, ranged=Server(archive))


def test_an_expired_signed_url_is_resolved_again(tmp_path, archive, monkeypatch):
    monkeypatch.setattr(zipranges, "BLOCK", 1024)
    server = Server(archive, expire_after=2)
    folder = zipranges.fetch_members(URL, ["xyz_admin1.shp"], tmp_path, ranged=server)
    assert (folder / "xyz_admin1.shp").read_bytes() == b"shapes" * 1000
    assert [u for u, _, _ in server.calls].count(URL) == 2  # the first resolve and one more


def test_a_server_that_ignores_ranges_is_refused(tmp_path, archive):
    def short(url, start, end):
        return archive[start : end + 1][:-1] if end > start else archive[:1], len(archive), FINAL

    with pytest.raises(ValueError, match="asked for"):
        zipranges.fetch_members(URL, ["xyz_admin1.dbf"], tmp_path, ranged=short)


def test_members_can_be_chosen_from_the_zip_listing_and_then_need_no_network(tmp_path, archive):
    def admin1(names):
        return [n for n in names if n.startswith("xyz_admin1.")]

    zipranges.fetch_members(URL, admin1, tmp_path, ranged=Server(archive))
    meta = json.loads((tmp_path / "xyz_admin_boundaries.shp.members.json").read_text())
    assert set(meta["members"]) == {"xyz_admin1.shp", "xyz_admin1.dbf"}
    assert "xyz_admin4.shp" in meta["names"]
    offline = Server(archive)
    zipranges.fetch_members(URL, admin1, tmp_path, ranged=offline)
    assert offline.calls == []
