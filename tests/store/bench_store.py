"""Store and config benchmark (not collected by pytest):

    uv run python tests/store/bench_store.py [PACKS_DIR]

PACKS_DIR holds built pack directories (<name>-<version>/; default ~/.placewise/packbuild/out),
which are only read. Prints the cold-start steps a first `placewise.lookup()` takes before the
engine opens a pack (imports, load_settings, load_overrides, Store.ensure), each in a fresh
interpreter (best of 5), and the time to re-hash every pack as `placewise data verify` does (best
of 3, so the files are in the page cache).
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

COLD = """
import time
t0 = time.perf_counter()
import placewise.config
t1 = time.perf_counter()
settings = placewise.config.load_settings()
t2 = time.perf_counter()
import placewise.overrides
t3 = time.perf_counter()
placewise.overrides.load_overrides(settings=settings)
t4 = time.perf_counter()
import placewise.store
t5 = time.perf_counter()
placewise.store.Store(settings=settings.data).ensure("world")
t6 = time.perf_counter()
print(t1 - t0, t2 - t1, t3 - t2, t4 - t3, t5 - t4, t6 - t5)
"""
STEPS = ("import placewise.config", "load_settings()", "import placewise.overrides", "load_overrides()")
STEPS += ("import placewise.store", "Store().ensure('world')")


def cold_start(packs_dir):
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data"
        (data / "packs").mkdir(parents=True)
        world = next(p for p in sorted(packs_dir.iterdir()) if p.name.startswith("world-"))
        (data / "packs" / world.name).mkdir()  # ensure() only lists directories
        (data / "packs" / world.name / "pack.json").write_bytes((world / "pack.json").read_bytes())
        config = Path(tmp) / "placewise.toml"
        config.write_text("[data]\noffline = true\n")
        env = {**os.environ, "PLACEWISE_DATA_DIR": str(data), "PLACEWISE_CONFIG": str(config)}
        best = None
        for _ in range(5):
            out = subprocess.run([sys.executable, "-c", COLD], env=env, capture_output=True, text=True)
            if out.returncode:
                raise SystemExit(out.stderr)
            times = tuple(map(float, out.stdout.split()))
            best = times if best is None else tuple(map(min, best, times))
    for step, t in zip(STEPS, best, strict=True):
        print(f"{step:30} {t * 1000:8.1f} ms")
    print(f"{'total':30} {sum(best) * 1000:8.1f} ms")


def verify(packs_dir):
    from placewise.store import archive

    packs = [p for p in sorted(packs_dir.iterdir()) if (p / "pack.json").is_file()]
    size = sum(f.stat().st_size for p in packs for f in p.rglob("*") if f.is_file())
    best, problems = None, None
    for _ in range(3):
        t = time.perf_counter()
        problems = [archive.check_pack_dir(p, *p.name.rsplit("-", 1), "its directory name") for p in packs]
        dt = time.perf_counter() - t
        best = dt if best is None else min(best, dt)
    rate = size / 1e6 / best
    print(f"verify {len(packs)} packs, {size / 1e6:,.0f} MB    {best:8.3f} s  = {rate:,.0f} MB/s")
    print(f"problems: {sum(map(len, problems))}")


def main():
    default = Path.home() / ".placewise" / "packbuild" / "out"
    packs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    if not packs_dir.is_dir():
        raise SystemExit(f"no packs directory at {packs_dir}")
    cold_start(packs_dir)
    verify(packs_dir)


if __name__ == "__main__":
    main()
