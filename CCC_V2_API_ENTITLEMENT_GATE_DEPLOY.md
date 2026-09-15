# CCC V2 API entitlement gate

Status: additive security hardening for V2 API.

## Security contract

- `/v1/quote/<SYMBOL>` remains public Market Quote.
- `/v1/chart/<SYMBOL>` requires a valid Supabase user JWT and technical entitlement.
- `/v1/access/<SYMBOL>` requires a valid Supabase user JWT and returns only the minimal access decision.
- `/health` is private-network only; do not expose it through the public Nginx bridge.
- The API uses the Supabase publishable key only. No `service_role` key is required.
- Entitlement failure is fail-closed: no protected chart data is returned if Supabase auth/RPC is unavailable.
- Authorization source of truth is `public.get_my_technical_access(text)`.

## Entitlement rules

The RPC follows current CCC product rules:

- FULL Market -> allowed for all known scanner symbols.
- Active VIP access pass -> allowed for all known scanner symbols.
- FREE/BASIC/PLUS/PRO -> symbol must be `base_active=true` in the user's Watchlist.
- Suspended/inactive accounts -> denied.
- Invalid/expired JWT -> denied.

## Nginx bridge after backend deploy

Inside the existing `location ^~ /api/v2/ { ... }`:

1. Remove the public health rewrite:
   `rewrite ^/api/v2/health$ /health break;`
2. Keep:
   `rewrite ^/api/v2/chart/(.+)$ /v1/chart/$1 break;`
   `rewrite ^/api/v2/quote/(.+)$ /v1/quote/$1 break;`
3. Add:
   `rewrite ^/api/v2/access/(.+)$ /v1/access/$1 break;`
4. Explicitly forward:
   `proxy_set_header Authorization $http_authorization;`

Expected behavior:

- `GET /api/v2/quote/HPG` without auth -> 200
- `GET /api/v2/chart/HPG?...` without auth -> 401
- `GET /api/v2/access/HPG` without auth -> 401
- `/api/v2/health` -> 404
- Authenticated + entitled chart -> 200
- Authenticated + outside entitlement -> 403

The frontend must send:
`Authorization: Bearer <supabase_access_token>`
for protected endpoints.
