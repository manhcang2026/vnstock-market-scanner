# Stock Detail V3: dev / VPS proxy parity

Frontend requests remain same-origin: HTTP under `/api/v2/` and the public chart WebSocket at `/api/v2/live`. No VPS address belongs in the browser bundle. The following is a deployment **snippet only**; this task does not apply or reload Nginx.

## Local development

Copy `.env.example` to ignored `.env.local` and fill in reachable private/VPN targets:

```dotenv
CCC_DEV_API_TARGET=http://<private-host>:8787
CCC_DEV_WS_TARGET=ws://<private-host>:8790
```

Vite requires both targets for `npm run dev`; it does not fall back to the old public domain. These variables have no `VITE_` prefix and are used only by Vite's development proxy, not client code or the production build. The HTTP proxy rewrites `/api/v2/quote/HPG` to `/v1/quote/HPG` (likewise chart, access, stock-detail, ccc, radar), preserving the query string and Authorization header. The WebSocket proxy forwards `/api/v2/live` to the separate WS target with Upgrade support. It does not proxy `/health`.

## Production Nginx routing

Place the exact WebSocket location before the general HTTP location in the applicable HTTPS `server` block. Adjust only the existing static root/TLS configuration separately; do not expose backend health endpoints.

```nginx
location = /api/v2/live {
    proxy_pass http://127.0.0.1:8790;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 65s;
}

location = /api/v2/health { return 404; }

location /api/v2/ {
    # Trailing slashes rewrite /api/v2/* to the chart API's /v1/* paths.
    proxy_pass http://127.0.0.1:8787/v1/;
    proxy_set_header Host $host;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Keep `/health` private; do not add a public location for it. Deploy the `npm run build` output as static files with the existing SPA fallback. Neither the production frontend nor Nginx needs `CCC_DEV_*`. The chart WebSocket subscription payload remains unchanged and carries no token for public chart data.
