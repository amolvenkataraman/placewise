"""Loading the override layers: the shipped repo files, the calling app's rules and the user's own
file."""

from pathlib import Path

from placewise.config import _toml
from placewise.constants import overrides as const
from placewise.model import Layer, OverrideSet

from .engine import OverrideEngine

REPO_DIR = Path(__file__).parent / "repo"


def load_overrides(repo_dir=None, local_path=None, app_rules=None, *, settings=None):
    """The override engine for this install.

    repo_dir:   directory of shipped rule files (default: placewise/overrides/repo); must exist.
    local_path: the user's file (default: the data directory's overrides.toml, or its .json twin,
                if present); False skips the local layer; a path given explicitly must exist.
    app_rules:  rules from the calling app: one document dict, an OverrideSet, or a list of them.
    settings:   Settings whose data.data_dir locates the default local file.
    """
    sets = []
    repo = REPO_DIR if repo_dir is None else Path(repo_dir)
    if not repo.is_dir():
        raise FileNotFoundError(f"overrides repo directory not found: {repo}")
    for path, cited in _repo_files(repo):
        sets.append((_read_set(Layer.REPO, path, f"repo:{cited}"), path.parent))

    if app_rules is not None:
        items = app_rules if isinstance(app_rules, list | tuple) else [app_rules]
        for i, item in enumerate(items, 1):
            if isinstance(item, OverrideSet):
                sets.append(item)
            else:
                sets.append(OverrideSet.from_dict(Layer.APP, item, "app" if len(items) == 1 else f"app:{i}"))

    local = _local_file(local_path, settings)
    if local is not None:
        sets.append((_read_set(Layer.LOCAL, local, f"local:{local.name}"), local.parent))
    return OverrideEngine(sets)


def _repo_files(directory):
    """(file to read, name to cite) per rule file. A .toml with a .json twin reads the twin where
    TOML can't be read (3.10 without tomli) but is cited as the .toml either way."""
    stems = sorted({p.stem for p in directory.iterdir() if p.is_file() and p.suffix in const.FILE_SUFFIXES})
    have_toml = _toml.available()
    out = []
    for stem in stems:
        toml, json = directory / f"{stem}.toml", directory / f"{stem}.json"
        if toml.exists():
            out.append((toml if have_toml or not json.exists() else json, toml.name))
        else:
            out.append((json, json.name))
    return out


def _local_file(local_path, settings):
    if local_path is False:
        return None
    if local_path is not None:
        path = Path(local_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"local overrides file not found: {path}")
        return path
    from placewise.store.paths import Layout, resolve_data_dir

    path = Layout(resolve_data_dir(settings=settings.data if settings is not None else None)).overrides
    for candidate in (path, path.with_suffix(".json")):
        if candidate.is_file():
            return candidate
    return None


def _read_set(layer, path, origin):
    try:
        doc = _toml.load(path)
    except _toml.TomlUnavailableError:
        raise
    except ValueError as e:
        raise ValueError(f"{origin}: {e}") from None
    try:
        return OverrideSet.from_dict(layer, doc, origin)
    except ValueError as e:
        raise ValueError(f"{path}: {e}") from None
