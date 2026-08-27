CCC v19.11.5 — MOBILE AUTH HOTFIX

Scope:
- Fix mobile login/signup input losing focus when the soft keyboard opens.
- Keep Zalo popup unchanged.
- Keep Supabase auth/data logic unchanged.
- Keep the production core app JS unchanged.

Cause:
- Core app has a global window resize handler that calls render().
- Mobile virtual keyboard opening changes viewport height and fires resize.
- render() replaces #app.innerHTML, destroying/recreating the auth dialog/input.
- auth CSS also expects body.ccc-auth-open for scroll lock, but the integrated app does not toggle it.

Implementation:
- A tiny guard script loads BEFORE the core app.
- While .ccc-auth-overlay exists, resize propagation is stopped before the
  core app resize handler runs.
- The guard toggles body.ccc-auth-open to restore modal scroll locking.

Files:
- website-next/assets/mobile-auth-hotfix-v19.11.5.js
- website-next/index.html
- website-next/VERSION.txt

No SQL / Supabase / Zalo changes.
