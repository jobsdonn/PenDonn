#!/usr/bin/env python3
"""Generate a basic_auth password_hash for config.json.local.

Standalone — only depends on werkzeug (already in the venv).
Replaces `python web/app.py --hash-password` from Phase 1E so the legacy
Flask UI can be retired without losing this operator workflow.

Usage:
    python3 scripts/hash-password.py            # interactive (recommended)
    python3 scripts/hash-password.py --pw '...' # one-shot, NOT for prod logs
"""

import getpass
import sys

try:
    from werkzeug.security import generate_password_hash
except ImportError:
    print("werkzeug not installed. From repo root:", file=sys.stderr)
    print("  ./venv/bin/python3 scripts/hash-password.py", file=sys.stderr)
    sys.exit(2)


def main() -> int:
    pw = None
    if len(sys.argv) >= 3 and sys.argv[1] == "--pw":
        pw = sys.argv[2]
        print("WARNING: password supplied via argv; will appear in shell history",
              file=sys.stderr)
    else:
        pw = getpass.getpass("Password: ")
        pw2 = getpass.getpass("Confirm:  ")
        if pw != pw2:
            print("Passwords don't match.", file=sys.stderr)
            return 1
    if len(pw) < 8:
        print("Refusing: password must be at least 8 characters.", file=sys.stderr)
        return 1
    print(generate_password_hash(pw))
    print(
        "\nAdd / replace under web.basic_auth.password_hash in "
        "config/config.json.local on the device.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
