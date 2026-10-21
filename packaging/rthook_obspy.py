"""Runtime hook: keep ObsPy's virtual package path inside the bundle.

ObsPy's ``core/util/version.py`` does ``inspect.getfile(currentframe())``
and derives ``OBSPY_ROOT`` from it. In a frozen app the code filename is
relative (``obspy/core/util/version.py``) or an absolute build-machine path,
so it looks for ``RELEASE-VERSION`` outside the bundle.

Remap only that virtual path to the extracted bundle root where
``obspy/RELEASE-VERSION`` and ``obspy/lib`` live. Normal source runs are
untouched because ``sys._MEIPASS`` is absent.
"""

from __future__ import annotations

import inspect
import os
import sys

_ORIG_GETFILE = inspect.getfile
_MARKER = "/obspy/"


def _getfile(obj):
    path = _ORIG_GETFILE(obj)
    if not isinstance(path, str):
        return path
    norm = path.replace("\\", "/")
    if norm.startswith("obspy/"):
        rel = norm[len("obspy/"):]
    elif _MARKER in norm:
        rel = norm.split(_MARKER, 1)[1]
    else:
        return path

    meipass = getattr(sys, "_MEIPASS", "")
    if not meipass:
        return path
    roots = [meipass, os.path.join(os.path.dirname(meipass), "Resources")]
    for root in roots:
        if os.path.exists(os.path.join(root, "obspy", "RELEASE-VERSION")):
            return os.path.join(root, "obspy", rel)
    return path


inspect.getfile = _getfile
