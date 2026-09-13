# AGENTS.md — SSI Realtime Shadow Service

These instructions apply to `services/ssi_realtime_shadow/**`.

- `docs/product/CCC_V2_PRODUCT_ENGINE_SPEC_v2.0.md` is the authority for the CCC V2 engine.
- The root-level legacy four-signal rules are superseded for this service only.
- Preserve the working SSI ingest; extend it rather than rewriting it.
- Do not make frontend changes during backend jobs.
- Do not commit credentials, tokens, keys, or other secrets.
- Production signal thresholds and weights must remain private and server-side.
- Every market-session change requires deterministic tests, including exact boundary behavior.
