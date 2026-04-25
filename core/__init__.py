"""PenDonn core package.

Submodules are imported on demand — `from core.<module> import <name>` —
rather than eagerly here, so that importing one submodule (e.g. core.safety,
core.database) does not pull in optional heavy deps like scapy or RPi.GPIO.
"""
