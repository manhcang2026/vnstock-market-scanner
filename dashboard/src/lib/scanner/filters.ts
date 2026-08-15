import type { FilterKey, SortKey, StockRow } from "./types";

export const EXCHANGE_FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "Tất cả sàn" },
  { key: "hose", label: "HOSE" },
  { key: "hnx", label: "HNX" },
  { key: "upcom", label: "UPCOM" },
];

export const SIGNAL_FILTERS: { key: FilterKey; label: string }[] = [
  { key: "4of4", label: "4/4 tín hiệu" },
  { key: "3plus", label: "Từ 3/4 trở lên" },
  { key: "exactly2", label: "Đúng 2/4" },
  { key: "exactly1", label: "Đúng 1/4" },
  { key: "rvol30", label: "RVOL30 ≥ 200%" },
  { key: "price3", label: "Giá ≥ 3%" },
  { key: "vol200", label: "KL ngày ≥ 200%" },
  { key: "abovema200", label: "Trên MA200" },
  { key: "missing", label: "Thiếu dữ liệu" },
];

export const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: "signal", label: "Ưu tiên tín hiệu" },
  { key: "rvol30", label: "RVOL30 cao nhất" },
  { key: "change", label: "% tăng cao nhất" },
  { key: "volume", label: "KL ngày cao nhất" },
  { key: "symbol", label: "Mã A–Z" },
];

function matchesSignalFilter(row: StockRow, key: FilterKey): boolean {
  switch (key) {
    case "4of4":
      return row.signalCount === 4;
    case "3plus":
      return row.signalCount >= 3;
    case "exactly2":
      return row.signalCount === 2;
    case "exactly1":
      return row.signalCount === 1;
    case "rvol30":
      return row.signalRvol30_200pct;
    case "price3":
      return row.signalPrice3pct;
    case "vol200":
      return row.signalVolume200pct;
    case "abovema200":
      return row.signalAboveMa200;
    case "missing":
      return row.hasMissingData;
    default:
      return true;
  }
}

export interface FilterState {
  search: string;
  exchange: FilterKey;
  signal: FilterKey | null;
}

export function applyFilters(rows: StockRow[], state: FilterState): StockRow[] {
  const q = state.search.trim().toUpperCase();
  return rows.filter((row) => {
    if (q && !row.symbol.toUpperCase().includes(q)) return false;
    if (state.exchange !== "all" && row.exchange.toLowerCase() !== state.exchange) return false;
    if (state.signal && !matchesSignalFilter(row, state.signal)) return false;
    return true;
  });
}

const n = (v: number | null) => (v === null || Number.isNaN(v) ? -Infinity : v);

/** Ưu tiên mặc định: RVOL30 ≥ 200% → signalCount → RVOL30 → %giá → KL ngày. */
function defaultPriority(a: StockRow, b: StockRow): number {
  if (a.signalRvol30_200pct !== b.signalRvol30_200pct) return a.signalRvol30_200pct ? -1 : 1;
  if (a.signalCount !== b.signalCount) return b.signalCount - a.signalCount;
  if (n(a.rvol30Pct) !== n(b.rvol30Pct)) return n(b.rvol30Pct) - n(a.rvol30Pct);
  if (n(a.changePct) !== n(b.changePct)) return n(b.changePct) - n(a.changePct);
  if (n(a.dayVolumeRatioPct) !== n(b.dayVolumeRatioPct))
    return n(b.dayVolumeRatioPct) - n(a.dayVolumeRatioPct);
  return a.symbol.localeCompare(b.symbol);
}

export function applySorting(rows: StockRow[], sort: SortKey): StockRow[] {
  const out = [...rows];
  switch (sort) {
    case "rvol30":
      return out.sort((a, b) => n(b.rvol30Pct) - n(a.rvol30Pct) || defaultPriority(a, b));
    case "change":
      return out.sort((a, b) => n(b.changePct) - n(a.changePct) || defaultPriority(a, b));
    case "volume":
      return out.sort(
        (a, b) => n(b.dayVolumeRatioPct) - n(a.dayVolumeRatioPct) || defaultPriority(a, b),
      );
    case "symbol":
      return out.sort((a, b) => a.symbol.localeCompare(b.symbol));
    case "signal":
    default:
      return out.sort(defaultPriority);
  }
}
