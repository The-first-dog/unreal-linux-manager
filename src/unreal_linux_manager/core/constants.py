"""Shared constant values (official URLs, labels) used across the app.

Only *official* Epic / Unreal Engine URLs are referenced. The application never
points to unofficial download mirrors and never redistributes the engine.
"""

from __future__ import annotations

# Official Unreal Engine download / Linux documentation.
UNREAL_DOWNLOAD_URL = "https://www.unrealengine.com/en-US/linux"
UNREAL_LINUX_DOC_URL = (
    "https://dev.epicgames.com/documentation/en-us/unreal-engine/"
    "linux-development-quickstart-for-unreal-engine"
)

# Bazzite / atomic desktop help.
BAZZITE_HELP_URL = "https://docs.bazzite.gg/"

# Legendary project page (reference / manual help).
LEGENDARY_HELP_URL = "https://github.com/derrod/legendary"

# Epic login helper used by Legendary. After logging in, Epic returns a JSON
# page containing an "authorizationCode" the user pastes back into the app.
# This is the exact helper URL that ``legendary auth`` itself points users to.
LEGENDARY_AUTH_URL = "https://legendary.gl/epiclogin"
