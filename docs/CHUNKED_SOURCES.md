# Chunked sources

Admin routes and the platform bot are split into UTF-8 text chunks so MCP
`push_files` stays under ~15–18KB per push.

| Assembler | Chunks | Notes |
|-----------|--------|-------|
| `app/admin_routes.py` | `app/_admin_r0.txt` … `_admin_r3.txt` | `exec` at import; wave mounts wrap `mount_admin` |
| `app/platform_bot.py` | `app/_pb_c0.txt` … `_pb_c11.txt` | same pattern |

Prefer **new small modules** (`app/wave*.py`, `app/coupons.py`, …) over rewriting
chunks. To rebuild a single file locally for review:

```bash
python scripts/assemble_chunks.py admin > /tmp/admin_routes_full.py
python scripts/assemble_chunks.py platform_bot > /tmp/platform_bot_full.py
```

Do not commit the assembled full files; keep chunks as the source of truth.
