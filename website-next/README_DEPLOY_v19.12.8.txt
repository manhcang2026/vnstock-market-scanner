CCC v19.12.8 — HAWKHOST DEPLOY PACKAGE
======================================

Target directory:
  /home/visasgn1/chuyenchochung.com/

The ZIP contents are rooted for direct extraction into the target directory.

Deploy order:
1. Extract/upload the files under assets/ first.
2. Replace VERSION.txt.
3. Replace index.html last to activate the release.

Included runtime files:
- assets/app-v19.12.8-golden-board.js
- assets/ccc-v19.12.8-responsive-lock.css
- assets/ccc-v19.12.8-responsive-lock.js
- VERSION.txt
- index.html

Do not run Supabase SQL for this frontend deployment.
Do not modify or delete stock-logos/.
Do not delete older JS/CSS assets; they are retained for rollback.

Post-deploy checks:
- VERSION.txt reports v19.12.8-responsive-lock.
- Homepage loads in a private/incognito window.
- /bang-vang works for guest and signed-in VIP/FULL users.
- Desktop and mobile navigation show Bang vang correctly.
- Light and dark themes remain usable.
- /danh-sach, /so-sanh-theo-nganh and /sang-loc-co-ban still work.
- Login, account and Watchlist flows still work.

Rollback:
1. Restore the backed-up v19.11.5 index.html.
2. Restore the backed-up v19.11.5 VERSION.txt.
3. The new versioned assets may remain on the server because the old index does
   not reference them.
