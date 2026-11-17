"""The worldview lock: which order one request gets once an operator has locked it."""

from .errors import ConfigError


class WorldviewLockedError(ConfigError):
    """Something tried to change a worldview the operator locked."""


def effective_worldview(settings, requested=None):
    """(order, locked) for one request. Without a lock a requested order wins; with one the
    operator's order stands, and a different request is ignored (conflict = "ignore") or refused
    (conflict = "reject")."""
    view = settings.worldview
    wanted = tuple(requested) if requested else None
    if not view.lock:
        if wanted is None:
            return view.order, False
        return type(view)(order=wanted).order, False  # validates the request
    if wanted is not None and wanted != view.order and view.conflict == "reject":
        raise WorldviewLockedError(
            f"this instance's worldview is locked to {list(view.order)}; requested {list(wanted)}"
        )
    return view.order, True
