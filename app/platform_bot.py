from __future__ import annotations
"""Assemble platform_bot from hex parts (MCP-safe upload)."""
from app._bot_hex_0 import HEX as H0
from app._bot_hex_1 import HEX as H1
from app._bot_hex_2 import HEX as H2
from app._bot_hex_3 import HEX as H3
from app._bot_hex_4 import HEX as H4
from app._bot_hex_5 import HEX as H5
from app._bot_hex_6 import HEX as H6
from app._bot_hex_7 import HEX as H7
exec(bytes.fromhex(H0 + H1 + H2 + H3 + H4 + H5 + H6 + H7).decode(), globals())
