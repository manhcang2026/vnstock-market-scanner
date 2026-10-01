# CCC V4 Shell Layout — Beta 10/10

**Status:** Product direction approved 2026-10-01  
**Supersedes:** the fixed V3 shell geometry where it conflicts with this document.

## 1. One shared application shell

All primary V4 routes use one shared App Shell.

Do not maintain separate page-level shells for Scanner, Stock Detail, Account, or other primary routes.

The shell owns:

- top bar;
- global left sidebar;
- center workspace;
- contextual right rail;
- desktop/mobile responsive transitions;
- global search;
- account entry;
- mobile hamburger navigation.

Stock Detail is a route inside this shell, not a separate shell.

## 2. Desktop geometry

V4 uses a true three-column workspace.

Recommended desktop geometry:

```text
TOP BAR: 52–56px

LEFT SIDEBAR | CENTER WORKSPACE | RIGHT CONTEXT
~224px       | minmax(0, 1fr)   | ~288–320px
```

Recommended CSS direction:

```css
grid-template-columns:
  224px
  minmax(0, 1fr)
  clamp(288px, 19vw, 320px);
gap: 10px 12px;
```

Responsive targets:

- >= 1440px: full 3-column workspace;
- 1280–1439px: compact 3-column, left about 200–208px, right about 260–280px;
- 1024–1279px: left + center, right context becomes panel/drawer/tab;
- <= 900px: center is 100%; left and right are not permanently visible.

Do not introduce a route-specific max-width container that creates large gutters or route-to-route horizontal jitter.

## 3. Left sidebar

The left column is global navigation/workspace, not a route-specific filter rail.

Beta routes may temporarily retain the current product IA:

- Tổng quan;
- Bộ quét / Danh sách;
- Nghiên cứu / So sánh ngành;
- Sàng lọc cơ bản;
- Tài khoản.

Reserve a personal area for:

- Danh sách theo dõi;
- additional watchlists later.

The structure must allow future items such as Market, CCC Scanner, AI Search, Articles, Community, Tools, and Academy without a shell rewrite.

## 4. Center workspace

The center is the primary working area.

Examples:

- Market / Watchlist: dense desktop table;
- Stock Detail: quote, chart, CCC Intelligence, signals, Fundamental, BCTC;
- Account: profile/package/watchlist management.

Scanner filters and sorting do not permanently consume the global left sidebar. They belong to a center toolbar and open a panel/popover/sheet.

## 5. Right contextual rail

The right rail is contextual, not primary navigation.

Examples:

### Market / Watchlist
- market indices/context;
- AI Search;
- later: featured articles / news;
- later: quick tools.

### Stock Detail
- session/quote context;
- related CCC context;
- AI “ask about this symbol” when implemented;
- compact data-trust/signal context when useful.

Do not render dead controls as if they work.

## 6. Mobile

Mobile is intentionally redesigned, not a scaled desktop table.

Top bar:

```text
☰   CCC / logo      Search      Account
```

The hamburger must work and contain the complete primary navigation.

A bottom navigation may remain as a shortcut set, but it does not replace the hamburger.

Rules:

- no permanent left sidebar;
- no permanent right rail;
- Market/Watchlist uses cards;
- filters/sort use bottom sheet or full-height sheet;
- market context may use a horizontal strip;
- touch targets should be at least 44px where practical.

## 7. Theme

Beta 10/10 uses one canonical dark theme.

Remove Light/Dark toggle presentation from the Beta shell.

The visual direction keeps CCC’s existing identity:

- near-black/navy page background;
- dark navy surfaces;
- thin blue-gray borders;
- off-white primary text;
- blue-gray secondary text;
- green positive;
- coral/red negative;
- blue/cyan public technical/action accents;
- violet/purple CCC/RVOL intelligence accents.

## 8. Migration rule

Reuse working V3 pieces where practical:

- React/Vite application;
- routing;
- auth;
- global stock search;
- chart engine;
- live WebSocket;
- StockLogo;
- scanner data utilities;
- mobile-card direction;
- Fundamental/BCTC clients.

Do not rewrite the frontend from zero.

The V4 implementation priority is to unify shell ownership and navigation first, then migrate route content into that shell.
