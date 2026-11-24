"""The running Runner's private socket: its name, and what travels over it.

Each user gets their own socket, which only they can open. A second copy of
Runner connects and writes anything that is not JSON ("show"), and the first
copy comes forward. `runner ctl` connects and writes one JSON request ending
in a newline; Runner answers with one JSON reply ending in a newline, then
hangs up. The requests are runner.api's.

This module stays free of the UI so `runner ctl` starts quickly.
"""

from __future__ import annotations

import hashlib
import os
import sys

# A request bigger than this is refused rather than read.
MAX_REQUEST_BYTES = 1_000_000
# A client that connects and goes quiet mid-request is dropped after this long.
REQUEST_TIMEOUT_MS = 5000


def _single_instance_name() -> str:
    """Where the single-instance socket lives. Private to this user.

    The name carries a hash of the user name, so two people signed in to one
    machine each get their own Runner. On Linux the socket goes in
    XDG_RUNTIME_DIR, a folder only this user can open; the shared /tmp would
    let another user claim the name first and stop Runner from starting.
    macOS already puts it in the per-user TMPDIR. On Windows it is a named
    pipe, and the session mutex decides which copy runs.
    """
    try:
        import getpass

        user = getpass.getuser()
    except (ImportError, KeyError, OSError):
        user = str(os.getuid()) if hasattr(os, "getuid") else "user"
    digest = hashlib.sha256(user.encode("utf-8")).hexdigest()[:12]
    name = f"Runner_SingleInstance_v2_{digest}"
    if sys.platform.startswith("linux"):
        runtime = os.environ.get("XDG_RUNTIME_DIR", "")
        if runtime and os.path.isdir(runtime):
            return os.path.join(runtime, name)
    return name


SINGLE_INSTANCE_SERVER = _single_instance_name()
