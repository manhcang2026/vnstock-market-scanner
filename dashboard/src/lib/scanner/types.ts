// Kiểu dữ liệu chuẩn hoá cho VNStock Market Scanner.
// Lớp này độc lập với nguồn dữ liệu (DEMO cục bộ hoặc Google Apps Script).

export type Exchange = "HOSE" | "HNX" | "UPCOM";

/** Trạng thái dữ liệu production của sheet Dashboard_Current (+ DEMO cục bộ). */
export type DataStatus =
  | "DEMO"
  | "OK"
  | "OUT_OF_SESSION_TEST"
  | "MISSING_MARKET_DATA"
  | (string & {});

/**
 * Bản ghi thô — ánh xạ 1-1 với các cột production của sheet Dashboard_Current.
 * Các cột tín hiệu (signal_*) chỉ có ở LIVE; ở DEMO được tính lại từ mock data.
 */
export interface RawStockRow {
  symbol: string;
  exchange: string;

  current_price: number | null;
  previous_close: number | null;
  price_change_pct?: number | null;

  volume_accumulated: number | null;
  avg_volume_10: number | null;
  avg_volume_sessions: number | null;
  daily_volume_pct?: number | null;

  ma200: number | null;
  ma200_sessions: number | null;
  ma200_distance_pct?: number | null;

  volume_30m: number | null;
  avg_volume_30m_10: number | null;
  rvol30_pct?: number | null;
  rvol30_sessions: number | null;

  signal_price_3pct?: boolean | number | string | null;
  signal_daily_volume_200pct?: boolean | number | string | null;
  signal_above_ma200?: boolean | number | string | null;
  signal_rvol30_200pct?: boolean | number | string | null;
  signal_count?: number | null;

  /** ISO, dd/MM/yyyy hoặc giá trị Date từ Apps Script */
  trading_date: string;
  /** "HH:mm-HH:mm", "HH:mm" hoặc chuỗi Date 1899 từ Apps Script */
  time_slot: string;
  updated_at: string;

  data_status: DataStatus;
  data_source?: string | undefined;
  note?: string | undefined;
}

/** Bản ghi đã chuẩn hoá + tính tín hiệu, dùng trực tiếp cho UI. */
export interface StockRow {
  symbol: string;
  exchange: Exchange | string;

  currentPrice: number | null;
  prevClose: number | null;
  /** % thay đổi so với giá đóng cửa phiên hoàn tất gần nhất */
  changePct: number | null;

  ma200: number | null;
  /** % khoảng cách so với MA200 */
  ma200DistancePct: number | null;
  ma200Sessions: number | null;

  cumVolume: number | null;
  avgVolume10: number | null;
  avgVolume10Sessions: number | null;
  /** Tỷ lệ KL ngày (%) = cumVolume / avgVolume10 */
  dayVolumeRatioPct: number | null;

  volume30m: number | null;
  avgVolume30mSameSlot: number | null;
  rvol30Pct: number | null;
  rvol30Sessions: number;

  signalPrice3pct: boolean;
  signalVolume200pct: boolean;
  signalAboveMa200: boolean;
  signalRvol30_200pct: boolean;
  signalCount: 0 | 1 | 2 | 3 | 4;

  isEarlyAlert: boolean;
  hasMissingData: boolean;

  /** dd/MM/yyyy */
  tradingDate: string;
  /** "HH:mm–HH:mm" hoặc "HH:mm" */
  timeSlot: string;
  /** HH:mm:ss (hoặc dd/MM/yyyy HH:mm:ss) */
  updatedAt: string;
  dataStatus: DataStatus;
  dataSource: string;
  note?: string | undefined;
}

export interface DashboardMeta {
  systemStatus: "OK" | "DEGRADED" | "ERROR";
  marketUpdatedAt: string;
  dashboardCheckedAt: string;
  totalSymbols: number;
  mode: "DEMO" | "LIVE";
  dataSource: string;
}

/** Payload JSON trả về từ Google Apps Script. */
export interface GasResponse {
  ok: boolean;
  error?: string;
  meta?: Partial<DashboardMeta>;
  rows?: RawStockRow[];
}

export interface DashboardData {
  meta: DashboardMeta;
  rows: StockRow[];
}

export type FilterKey =
  | "all"
  | "hose"
  | "hnx"
  | "upcom"
  | "4of4"
  | "3plus"
  | "exactly2"
  | "exactly1"
  | "rvol30"
  | "price3"
  | "vol200"
  | "abovema200"
  | "missing";

export type SortKey = "signal" | "rvol30" | "change" | "volume" | "symbol";
