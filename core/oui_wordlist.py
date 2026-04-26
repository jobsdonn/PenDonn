"""OUI-based PSK pre-guess wordlist generator.

Before exhausting a full dictionary, try a small targeted list derived from:
  1. Universal weak defaults (always tried)
  2. SSID-based patterns (SSID itself, common suffix variants)
  3. BSSID-based patterns (last-N-hex-digits — common on TP-Link, D-Link etc.)
  4. Vendor-specific patterns when the OUI matches a known manufacturer

The candidates are written to a temporary file so the existing cracker loop
can pass them to any engine (cowpatty/aircrack/john) without modification.

This catches a meaningful fraction of SOHO targets in the first few seconds
rather than hours into a rockyou run.  When no match, the cracker falls
through to the normal wordlists — no performance penalty.
"""

import os
import re
import tempfile
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OUI registry: first 6 hex chars of MAC (upper, no separators) → vendor tag
# Only vendors whose default PSKs have recognisable patterns are included.
# ---------------------------------------------------------------------------

# fmt: off
_OUI_VENDOR = {
    # TP-Link
    "D80D17": "tplink", "C8D3A3": "tplink", "AC15A2": "tplink",
    "B0487A": "tplink", "94D9B3": "tplink", "A0F3C1": "tplink",
    "F4F26D": "tplink", "E8DE27": "tplink", "30B49E": "tplink",
    "50C7BF": "tplink", "8C8D28": "tplink", "EC172F": "tplink",
    "F4EC38": "tplink", "A42BB0": "tplink", "CCA223": "tplink",
    "600E39": "tplink", "3C52A1": "tplink", "84169C": "tplink",
    # ASUS
    "107B44": "asus",   "2C56DC": "asus",   "D8508B": "asus",
    "50465D": "asus",   "70F11C": "asus",   "90E6BA": "asus",
    "BC4E8E": "asus",   "489FE9": "asus",   "000C6E": "asus",
    # Netgear
    "A021B7": "netgear", "E04F43": "netgear", "6CB0CE": "netgear",
    "206BEF": "netgear", "20E52A": "netgear", "9C3DCF": "netgear",
    "4C60DE": "netgear", "9003B7": "netgear",
    # D-Link
    "00265A": "dlink",  "1C7EE5": "dlink",  "84C9B2": "dlink",
    "B8A386": "dlink",  "C8BE19": "dlink",  "ECC8FD": "dlink",
    "F0B4D2": "dlink",  "B0C545": "dlink",
    # Linksys / Cisco Home
    "00E04C": "linksys", "0014BF": "linksys", "E06995": "linksys",
    "58EF68": "linksys", "202BC1": "linksys",
    # AVM Fritz!Box
    "3C:37:86": "fritzbox", "7C:4C:A5": "fritzbox", "E0:28:6D": "fritzbox",
    "E8:CC:18": "fritzbox", "A0:63:91": "fritzbox", "3C3786": "fritzbox",
    "7C4CA5": "fritzbox", "E0286D": "fritzbox", "E8CC18": "fritzbox",
    "A06391": "fritzbox", "BC0519": "fritzbox", "380A94": "fritzbox",
    # Huawei (ISP CPE)
    "0019CB": "huawei",  "40987E": "huawei",  "5479B2": "huawei",
    "7CC2C6": "huawei",  "941A22": "huawei",  "E8CD2D": "huawei",
    "48DB50": "huawei",  "64D9543": "huawei",
    # ZTE
    "7C8172": "zte",    "BC3BF2": "zte",    "F8F751": "zte",
    "7C7D3D": "zte",    "8C1222": "zte",
    # Tenda
    "C83A35": "tenda",  "D038DF": "tenda",  "1C87F4": "tenda",
    "00D0F8": "tenda",
    # Ubiquiti
    "B4FBE4": "ubiquiti", "0418D6": "ubiquiti", "788A20": "ubiquiti",
    "24A43C": "ubiquiti", "44D9E7": "ubiquiti",
    # Zyxel
    "001349": "zyxel",  "C0C1C0": "zyxel",  "002156": "zyxel",
    "90EFB8": "zyxel",  "C8B1CD": "zyxel",
    # Technicolor / Thomson (ISP boxes)
    "008EA4": "technicolor", "44E9DD": "technicolor", "E4B97A": "technicolor",
    "F0DCDE": "technicolor", "787B8A": "technicolor",
    # Vodafone/EasyBox
    "0018E7": "vodafone", "5C2791": "vodafone",
    # BT (Openreach HH3/HH5/SH2)
    "E86F38": "bt", "EC086B": "bt", "1C4D70": "bt",
}
# fmt: on


def _normalise_bssid(bssid: str) -> str:
    """Remove separators and uppercase."""
    return re.sub(r"[^0-9A-Fa-f]", "", bssid).upper()


def _lookup_vendor(bssid: str) -> Optional[str]:
    """Return a vendor tag for the given BSSID, or None."""
    norm = _normalise_bssid(bssid)
    if len(norm) < 6:
        return None
    oui = norm[:6]
    return _OUI_VENDOR.get(oui)


# ---------------------------------------------------------------------------
# Pattern generators
# ---------------------------------------------------------------------------

def _universal_weak() -> List[str]:
    return [
        "12345678", "87654321", "00000000", "11111111", "99999999",
        "123456789", "1234567890", "password", "Password1",
        "admin", "Admin1234", "root",
    ]


def _ssid_patterns(ssid: str) -> List[str]:
    """Patterns derived from the SSID string itself."""
    s = ssid.strip()
    if not s:
        return []
    candidates = [s]
    sl = s.lower()
    candidates.append(sl)
    candidates.append(s + "1")
    candidates.append(s + "123")
    candidates.append(s + "1234")
    candidates.append(s + "12345")
    candidates.append(s + "!")
    candidates.append(s + "2024")
    candidates.append(s + "2023")
    candidates.append(s + "@1")
    # If SSID looks like "SSID_XXXXXX" (e.g. "FRITZ!Box 7530 AB"), extract suffix
    parts = re.split(r"[\s_-]+", s)
    for p in parts:
        if len(p) >= 4:
            candidates.append(p)
    return [c for c in candidates if 8 <= len(c) <= 63]


def _bssid_patterns(bssid: str) -> List[str]:
    """BSSID-derived patterns common in cheap SOHO firmware.

    TP-Link: WPA key = last 8 uppercase hex digits of BSSID.
    D-Link:  WPA key = last 8 uppercase hex digits (some models).
    Others:  try both upper and lower for good measure.
    """
    norm = _normalise_bssid(bssid)
    if len(norm) < 8:
        return []
    last8 = norm[-8:]
    last6 = norm[-6:]
    last4 = norm[-4:]
    return [
        last8,
        last8.lower(),
        last6,
        last6.lower(),
        last4,
        last4.lower(),
        "tp-link_" + last8,       # TP-Link WPA default label pattern
        "TP-Link_" + last8,
    ]


def _vendor_patterns(vendor: str, bssid: str, ssid: str) -> List[str]:
    """Vendor-specific patterns beyond the generic ones."""
    norm = _normalise_bssid(bssid)
    last8 = norm[-8:] if len(norm) >= 8 else norm
    candidates: List[str] = []

    if vendor == "tplink":
        # TP-Link default: "tp-link_<last8upper>" or just last8
        candidates.extend([
            "tp-link_" + last8,
            "TP-Link_" + last8,
            last8, last8.lower(),
        ])
    elif vendor == "dlink":
        candidates.extend([last8, last8.lower()])
    elif vendor == "asus":
        # ASUS RT-N: key is "12345678" on many models, or SSID-based
        candidates.extend(["12345678", ssid, ssid + "1234"])
    elif vendor == "netgear":
        # Netgear: label key (varies, but "password" is common factory reset)
        candidates.extend(["password", "Passw0rd"])
    elif vendor == "linksys":
        # Factory shipped open or uses SSID = key
        candidates.extend(["", ssid, "admin"])
    elif vendor == "fritzbox":
        # Fritz!Box has a unique printed key — hard to guess without the device.
        # But some users reset to a predictable pattern.
        candidates.extend(["1234567890", "fritzbox"])
    elif vendor == "zte":
        candidates.extend(["12345678", last8, last8.lower()])
    elif vendor in ("huawei", "vodafone"):
        candidates.extend([last8, last8.lower(), "12345678"])
    elif vendor == "tenda":
        candidates.extend(["12345678", last8.lower()])
    elif vendor == "bt":
        # BT Hub 3/5/6: 10-char label key — last 10 hex of MAC is a known pattern
        last10 = norm[-10:] if len(norm) >= 10 else norm
        candidates.extend([last10.lower(), last10.upper()])

    return [c for c in candidates if c and 8 <= len(c) <= 63]


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def generate_oui_wordlist(bssid: str, ssid: str) -> Optional[str]:
    """Build a targeted mini-wordlist for this AP and write to a temp file.

    Returns the path to the temp file, or None if the list is empty.
    Caller is responsible for deleting the file after use.
    """
    vendor = _lookup_vendor(bssid)
    candidates: List[str] = []

    # Universal
    candidates.extend(_universal_weak())
    # SSID-derived
    candidates.extend(_ssid_patterns(ssid))
    # BSSID-derived
    candidates.extend(_bssid_patterns(bssid))
    # Vendor-specific
    if vendor:
        logger.debug(f"OUI match: {bssid[:8]} → {vendor}")
        candidates.extend(_vendor_patterns(vendor, bssid, ssid))

    # Deduplicate while preserving order, drop empties and length outliers.
    seen = set()
    unique = []
    for c in candidates:
        if c and c not in seen and 8 <= len(c) <= 63:
            seen.add(c)
            unique.append(c)

    if not unique:
        return None

    try:
        fd, path = tempfile.mkstemp(prefix="pendonn_oui_", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(unique) + "\n")
        logger.info(
            f"OUI wordlist for {ssid} ({bssid}): {len(unique)} candidates"
            + (f" [vendor={vendor}]" if vendor else "")
        )
        return path
    except OSError as e:
        logger.warning(f"Could not write OUI wordlist: {e}")
        return None
