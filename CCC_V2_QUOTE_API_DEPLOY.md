# CCC V2 realtime quote API overlay

Adds internal endpoint:

- `GET /v1/quote/<SYMBOL>`

The endpoint reads `latest_quotes` from `ssi_shadow.db` in SQLite read-only mode.
It does not call SSI and does not write Supabase.

After deploying to `ccc-realtime-01`, add this Nginx bridge line on `web-hosting-01`
inside the existing `location ^~ /api/v2/ { ... }` block:

```nginx
rewrite ^/api/v2/quote/(.+)$ /v1/quote/$1 break;
```

Expected public endpoint:

`https://chuyenchochung.com/api/v2/quote/HPG`
