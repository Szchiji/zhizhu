# XSS / HTML injection hardening

Card placeholders are escaped via `html.escape` in `app/card_tpl.py`.
Telegram card sends use `PARSE_MODE=HTML`.
Mini-app avoids `innerHTML` for user/admin fields.

Verify: put `<script>` or `<b onclick=...>` in card_text / display_name and confirm it shows as text.
