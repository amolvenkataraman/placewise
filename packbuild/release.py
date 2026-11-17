"""Prepare a data release from built packs and, only when asked twice, publish it with `gh`.

    uv run python -m packbuild.release --packs ~/.placewise/packbuild/out/world-2026.11 \\
        ~/.placewise/packbuild/out/usa-2026.11 --out ~/.placewise/packbuild/release/2026.11

writes, into --out, one `<name>-<version>.tar.xz` per pack, `index.json` (relative URLs),
`ATTRIBUTION.md` (only the sources these packs use, after the disclaimer), a copy of the repo's
`DISCLAIMER.md`, `SHA256SUMS`, and `release-notes.md` (the release description, not an asset). The
directory is a complete mirror. It then prints the `gh release create` command it would run.
`--publish` runs it, and is refused unless PLACEWISE_ALLOW_PUBLISH=1 is set as well.

Share-alike sources (placewise.constants.licences.SHARE_ALIKE) may only be in a share-alike pack,
one whose name ends in `-sa` (placewise.constants.packs.SHARE_ALIKE_SUFFIX); any other pack that
lists one is refused.
"""

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from placewise import attribution
from placewise.constants import packs as consts
from placewise.constants.store import PACK_VERSION_PATTERN
from placewise.model import PackInfo
from placewise.packs import archive, open_pack, pack_info, write_index

DATA_REPO = "amolvenkataraman/placewise-data"  # GitHub owner/name; releases hold the assets
ALLOW_PUBLISH_ENV = "PLACEWISE_ALLOW_PUBLISH"
ATTRIBUTION_FILE = "ATTRIBUTION.md"
DISCLAIMER_FILE = "DISCLAIMER.md"
DISCLAIMER = Path(__file__).resolve().parents[1] / DISCLAIMER_FILE  # the repo's; every release ships it
SUMS_FILE = "SHA256SUMS"
NOTES_FILE = "release-notes.md"
_REPO_PATTERN = r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+"


@dataclass(frozen=True)
class ReleasePlan:
    """A prepared release directory: what `publish` uploads and describes."""

    out_dir: Path
    packs: tuple[PackInfo, ...]  # in the order given
    archives: tuple[Path, ...]
    index: Path
    attribution: Path
    disclaimer: Path
    sums: Path
    notes: Path  # the release description, not uploaded

    @property
    def version(self) -> str:
        """The newest pack version: the default release tag."""
        return max((p.version for p in self.packs), key=_version_key)

    @property
    def assets(self) -> tuple[Path, ...]:
        """The files a release uploads, index first."""
        return (self.index, self.attribution, self.disclaimer, self.sums, *self.archives)


def prepare_release(pack_dirs, out_dir) -> ReleasePlan:
    """Check, archive and index the built packs in `pack_dirs` into `out_dir`. Everything is
    checked before anything is written; the pack directories are left as they are."""
    pack_dirs = [Path(p) for p in pack_dirs]
    out_dir = Path(out_dir)
    if not pack_dirs:
        raise ValueError("no packs to release")
    manifests = [_manifest(p) for p in pack_dirs]
    names = [m["name"] for m in manifests]
    if dupes := sorted({n for n in names if names.count(n) > 1}):
        raise ValueError(f"pack(s) given more than once: {', '.join(dupes)}")
    known = attribution.load_sources()
    for path, m in zip(pack_dirs, manifests, strict=True):
        if m["schema"] != consts.SCHEMA:
            raise ValueError(
                f"{path}: pack {m['name']!r} has schema {m['schema']}; "
                f"an index of schema {consts.SCHEMA} takes only schema-{consts.SCHEMA} packs"
            )
        expected = f"{m['name']}-{m['version']}"
        if path.name != expected:
            raise ValueError(f"{path}: pack {m['name']} {m['version']} must be in a directory {expected}")
        if unknown := [s for s in m["sources"] if s not in known]:
            raise ValueError(f"{path}: source(s) {', '.join(unknown)} are not in the source registry")
        share_alike = [s for s in m["sources"] if known[s].share_alike]
        if share_alike and not m["name"].endswith(consts.SHARE_ALIKE_SUFFIX):
            raise ValueError(
                f"{path}: pack {m['name']!r} carries share-alike source(s) {', '.join(share_alike)}; "
                f"they may only go in a share-alike pack, named <name>{consts.SHARE_ALIKE_SUFFIX}"
            )
        open_pack(path, verify=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    archives = tuple(_archive_into(p, out_dir) for p in pack_dirs)
    infos = tuple(pack_info(a) for a in archives)
    index = write_index(out_dir, infos)
    attr = out_dir / ATTRIBUTION_FILE
    used = dict.fromkeys(s for info in infos for s in info.sources)
    attr.write_text(attribution.render_markdown(only=used), encoding="utf-8")
    disclaimer = out_dir / DISCLAIMER_FILE
    shutil.copyfile(DISCLAIMER, disclaimer)
    sums = out_dir / SUMS_FILE
    listed = sorted((index, attr, disclaimer, *archives), key=lambda p: p.name)
    sums.write_text("".join(f"{_sha256(p)}  {p.name}\n" for p in listed), encoding="utf-8")
    notes = out_dir / NOTES_FILE
    notes.write_text(_notes(infos), encoding="utf-8")
    return ReleasePlan(out_dir, infos, archives, index, attr, disclaimer, sums, notes)


def publish(plan, repo=DATA_REPO, tag=None, dry_run=True):
    """The `gh release create` command for `plan`. dry_run (the default) prints it and runs
    nothing; dry_run=False runs it, and only when PLACEWISE_ALLOW_PUBLISH=1 is set."""
    tag = plan.version if tag is None else tag
    if not re.fullmatch(PACK_VERSION_PATTERN, tag):
        raise ValueError(f"tag {tag!r} must be a CalVer data version like 2026.11 or 2026.11.1")
    if not re.fullmatch(_REPO_PATTERN, repo):
        raise ValueError(f"repo {repo!r} must be a GitHub owner/name")
    cmd = [
        "gh", "release", "create", tag,
        "--repo", repo,
        "--title", f"placewise data {tag}",
        "--notes-file", str(plan.notes),
        "--latest",  # placewise reads releases/latest/download/index.json
        *[str(p) for p in plan.assets],
    ]  # fmt: skip
    print(shlex.join(cmd))
    if dry_run:
        return cmd
    if os.environ.get(ALLOW_PUBLISH_ENV) != "1":
        raise PermissionError(f"publishing uploads data; set {ALLOW_PUBLISH_ENV}=1 to allow it")
    if missing := [p.name for p in (plan.notes, *plan.assets) if not p.is_file()]:
        raise FileNotFoundError(f"release file(s) missing from {plan.out_dir}: {', '.join(missing)}")
    subprocess.run(cmd, check=True)
    return cmd


def _manifest(path):
    manifest = path / consts.PACK_JSON
    if not manifest.is_file():
        raise ValueError(f"{path} is not a pack (no {consts.PACK_JSON})")
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    for key in ("name", "version", "schema", "sources"):
        if key not in doc:
            raise ValueError(f"{manifest}: missing {key!r}")
    return doc


def _archive_into(pack_dir, out_dir):
    """archive() writes beside the pack; move the result into out_dir (copy if an archive was
    already there, so nothing next to the pack disappears)."""
    beside = pack_dir.parent / f"{pack_dir.name}{consts.ARCHIVE_SUFFIX}"
    existed = beside.exists()
    made = archive(pack_dir)
    target = out_dir / made.name
    if made.resolve() == target.resolve():
        return target
    (shutil.copyfile if existed else shutil.move)(made, target)
    return target


def _notes(infos):
    lines = ["Data packs for placewise. Install with `placewise data install <pack>`.", ""]
    lines += ["| Pack | Version | Size | Sources |", "|---|---|---|---|"]
    for p in infos:
        lines.append(f"| {p.name} | {p.version} | {p.size_bytes / 1e6:.1f} MB | {', '.join(p.sources)} |")
    lines += [
        "",
        f"Credits and licences: {ATTRIBUTION_FILE}. Checksums: {SUMS_FILE} and index.json. "
        "The data stays under its sources' licences.",
        "",
        f'Provided "as is" and "where is", with no warranty and no legal liability: {DISCLAIMER_FILE}.',
    ]
    return "\n".join(lines) + "\n"


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while chunk := fh.read(consts.HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _version_key(version):
    return tuple(int(part) for part in version.split("."))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m packbuild.release", description=__doc__.split("\n")[0])
    parser.add_argument(
        "--packs", nargs="+", type=Path, required=True, metavar="DIR", help="built pack directories"
    )
    parser.add_argument("--out", type=Path, required=True, metavar="DIR", help="release directory to write")
    parser.add_argument("--tag", help="release tag (default: the newest pack version)")
    parser.add_argument("--repo", default=DATA_REPO, help=f"GitHub owner/name (default {DATA_REPO})")
    parser.add_argument(
        "--publish", action="store_true", help=f"create the GitHub release (needs {ALLOW_PUBLISH_ENV}=1)"
    )
    args = parser.parse_args(argv)
    if args.publish and os.environ.get(ALLOW_PUBLISH_ENV) != "1":
        print(f"refusing to publish: set {ALLOW_PUBLISH_ENV}=1 as well as --publish", file=sys.stderr)
        return 2
    plan = prepare_release(args.packs, args.out)
    for path in (*plan.assets, plan.notes):
        print(f"{path.stat().st_size:>12,}  {path}")
    publish(plan, repo=args.repo, tag=args.tag, dry_run=not args.publish)
    return 0


if __name__ == "__main__":
    sys.exit(main())
