# CCC V3 desktop shell layout

## Fixed geometry

At desktop widths of 1200px and above, Stock Detail V3 is the reference for the reusable V2 shell:

```text
48px compact navigation | 240px left rail | minmax(0, 1fr) workspace | 240px right rail
```

- The compact navigation is fixed to the viewport edge below the 52px header. Page content starts immediately to its right.
- Both content rails use the same `--ccc-side-rail-width: 240px` token defined on `.stock-v3-shell`. A route must not silently assign its own left/right desktop widths.
- The center track consumes all remaining width with `minmax(0, 1fr)`; neither a max-width container nor an auto margin should create empty gutters or route-to-route jitter.
- The 48px navigation, 240px left rail, flexible center, and 240px right rail keep the same horizontal positions across V3 routes. Future Overview, Scanner, Signal Achievements, and Account layouts must follow this desktop track contract.
- The desktop content grid is at least the viewport height below the header. Side rails are top-aligned and may size to their own content; they do not stretch to match taller center content. Routes must not create large empty rail background slabs merely to equalize heights.
- Opening the navigation drawer overlays the content and replaces the visible compact rail. It must not push or resize the three content tracks.
- Below 1200px, a route may stack or adapt its slots to preserve usable workspace width. Mobile bottom navigation and safe-area padding remain separate from desktop geometry.

The current implementation applies these slots to Stock Detail only. Other routes are not migrated by this document. A future route should reuse the shell token and track contract when its three-column desktop layout is implemented.

## Slot examples for future routes

| Route | Left rail | Center workspace | Right rail |
| --- | --- | --- | --- |
| Stock Detail | Radar | Chart and tabs | Public quote/data context |
| Scanner | Filters | Results | AI search/context, only when implemented |
| Overview | Market pulse | Dashboard | Alerts, only when implemented |
| Signal Achievements | Filters | Cases | Stats, only when implemented |
| Account | Navigation | Profile and Watchlist | Package/account context, only when implemented |

These are layout slots, not authorization to create routes, fabricate data, or change entitlement. Stock Detail data ownership and permission boundaries remain defined by `CCC_DATA_SOURCE_OWNERSHIP.md`.
