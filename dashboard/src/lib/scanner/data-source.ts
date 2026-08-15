// ============================================================
// LỚP TẢI DỮ LIỆU
// Đây là ranh giới duy nhất giữa giao diện và nguồn dữ liệu.
// Chuyển DEMO -> LIVE: chỉ sửa 2 dòng cấu hình DATA_MODE và GAS_ENDPOINT bên dưới.
// ============================================================

import { DEMO_META, DEMO_ROWS } from "./demo-data";
import { formatTimeSlot, formatTradingDate, formatUpdatedAt } from "./format";
import type {
  DashboardData,
  DashboardMeta,
  GasResponse,
  RawStockRow,
  StockRow,
} from "./types";

// ⬇⬇ HAI DÒNG DUY NHẤT CẦN SỬA ĐỂ CHUYỂN DEMO -> LIVE ⬇⬇
export const DATA_MODE: "demo" | "live" = "demo";
export const GAS_ENDPOINT = "";
// ⬆⬆ ------------------------------------------------ ⬆⬆

/** Điểm nối duy nhất với Google Apps Script. */
async function fetchGas(): Promise<GasResponse> {
  if (!GAS_ENDPOINT) {
    throw new Error(
      "Chưa cấu hình GAS_ENDPOINT. Vui lòng điền URL Google Apps Script trong data-source.ts.",
    );
  }
  const res = await fetch(GAS_ENDPOINT, { method: "GET" });
  if (!res.ok) {
    throw new Error(`Không tải được dữ liệu từ Google Apps Script (HTTP ${res.status}).`);
  }
  const json = (await res.json()) as GasResponse;
  if (!json || json.ok !== true) {
    throw new Error(
      json?.error ?? "Google Apps Script trả về ok=false — dữ liệu không hợp lệ.",
    );
  }
  return json;
}

function num(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(String(value).replace(/[,%\s]/g, ""));
  return Number.isFinite(n) ? n : null;
}

function bool(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value === 1;
  if (typeof value === "string") {
    const v = value.trim().toUpperCase();
    return v === "TRUE" || v === "1" || v === "YES" || v === "X" || v === "ĐẠT";
  }
  return false;
}

function safeDiv(a: number | null, b: number | null): number | null {
  if (a === null || b === null || !Number.isFinite(a) || !Number.isFinite(b) || b === 0) return null;
  return a / b;
}

/**
 * Chuẩn hoá bản ghi thô -> bản ghi UI.
 * - LIVE: dùng signal_* / signal_count từ backend làm nguồn sự thật, không tính lại.
 * - DEMO: tính tín hiệu từ mock data.
 */
export function normalizeRows(raw: RawStockRow[], mode: "demo" | "live" = DATA_MODE): StockRow[] {
  const isLive = mode === "live";

  return raw.map((r) => {
    const currentPrice = num(r.current_price);
    const prevClose = num(r.previous_close);
    const ma200 = num(r.ma200);
    const cumVolume = num(r.volume_accumulated);
    const avgVolume10 = num(r.avg_volume_10);
    const volume30m = num(r.volume_30m);
    const avgVolume30mSameSlot = num(r.avg_volume_30m_10);
    const rvol30Sessions = num(r.rvol30_sessions) ?? 0;

    const computedChangePct = (() => {
      const ratio = safeDiv(
        currentPrice !== null && prevClose !== null ? currentPrice - prevClose : null,
        prevClose,
      );
      return ratio === null ? null : ratio * 100;
    })();
    const changePct = num(r.price_change_pct) ?? computedChangePct;

    const computedMa200DistancePct = (() => {
      const ratio = safeDiv(
        currentPrice !== null && ma200 !== null ? currentPrice - ma200 : null,
        ma200,
      );
      return ratio === null ? null : ratio * 100;
    })();
    const ma200DistancePct = num(r.ma200_distance_pct) ?? computedMa200DistancePct;

    const computedDayVolumePct = (() => {
      const ratio = safeDiv(cumVolume, avgVolume10);
      return ratio === null ? null : ratio * 100;
    })();
    const dayVolumeRatioPct = num(r.daily_volume_pct) ?? computedDayVolumePct;

    // Quy tắc: chưa có phiên tham chiếu -> KHÔNG hiển thị RVOL30 giả.
    const computedRvol30Pct = (() => {
      if (rvol30Sessions <= 0) return null;
      const ratio = safeDiv(volume30m, avgVolume30mSameSlot);
      return ratio === null ? null : ratio * 100;
    })();
    const rvol30Pct = rvol30Sessions <= 0 ? null : (num(r.rvol30_pct) ?? computedRvol30Pct);

    const signalPrice3pct = isLive
      ? bool(r.signal_price_3pct)
      : changePct !== null && changePct >= 3;
    const signalVolume200pct = isLive
      ? bool(r.signal_daily_volume_200pct)
      : dayVolumeRatioPct !== null && dayVolumeRatioPct >= 200;
    const signalAboveMa200 = isLive
      ? bool(r.signal_above_ma200)
      : currentPrice !== null && ma200 !== null && currentPrice > ma200;
    const signalRvol30_200pct =
      rvol30Sessions <= 0
        ? false
        : isLive
          ? bool(r.signal_rvol30_200pct)
          : rvol30Pct !== null && rvol30Pct >= 200;

    const computedCount = [
      signalPrice3pct,
      signalVolume200pct,
      signalAboveMa200,
      signalRvol30_200pct,
    ].filter(Boolean).length;
    const liveCount = num(r.signal_count);
    const signalCount = (
      isLive && liveCount !== null ? Math.max(0, Math.min(4, Math.round(liveCount))) : computedCount
    ) as 0 | 1 | 2 | 3 | 4;

    const hasMissingData =
      currentPrice === null ||
      prevClose === null ||
      ma200 === null ||
      cumVolume === null ||
      avgVolume10 === null ||
      r.data_status === "MISSING_MARKET_DATA" ||
      r.data_status === "MISSING" ||
      r.data_status === "ERROR";

    return {
      symbol: r.symbol,
      exchange: r.exchange,
      currentPrice,
      prevClose,
      changePct,
      ma200,
      ma200DistancePct,
      ma200Sessions: num(r.ma200_sessions),
      cumVolume,
      avgVolume10,
      avgVolume10Sessions: num(r.avg_volume_sessions),
      dayVolumeRatioPct,
      volume30m,
      avgVolume30mSameSlot,
      rvol30Pct,
      rvol30Sessions,
      signalPrice3pct,
      signalVolume200pct,
      signalAboveMa200,
      signalRvol30_200pct,
      signalCount,
      isEarlyAlert: signalRvol30_200pct,
      hasMissingData,
      tradingDate: formatTradingDate(r.trading_date),
      timeSlot: formatTimeSlot(r.time_slot),
      updatedAt: formatUpdatedAt(r.updated_at),
      dataStatus: r.data_status,
      dataSource: r.data_source ?? (isLive ? "Google Apps Script" : "Dữ liệu demo cục bộ"),
      note: r.note,
    } satisfies StockRow;
  });
}

function liveMeta(json: GasResponse, rows: RawStockRow[]): DashboardMeta {
  const latestUpdated = rows.reduce<string>((acc, r) => {
    const cur = formatUpdatedAt(r.updated_at);
    return cur > acc ? cur : acc;
  }, "");
  const now = new Date().toLocaleTimeString("vi-VN", { hour12: false });
  const hasIssue = rows.some(
    (r) => r.data_status === "MISSING_MARKET_DATA" || r.data_status === "ERROR",
  );

  return {
    systemStatus: json.meta?.systemStatus ?? (hasIssue ? "DEGRADED" : "OK"),
    marketUpdatedAt: json.meta?.marketUpdatedAt ?? (latestUpdated || "—"),
    dashboardCheckedAt: json.meta?.dashboardCheckedAt ?? now,
    totalSymbols: json.meta?.totalSymbols ?? rows.length,
    mode: "LIVE",
    dataSource: json.meta?.dataSource ?? "Google Apps Script",
  };
}

/** Hàm tải dữ liệu chính cho toàn bộ Dashboard. */
export async function loadDashboardData(): Promise<DashboardData> {
  if (DATA_MODE === "live") {
    const json = await fetchGas();
    const rows = json.rows ?? [];
    return { meta: liveMeta(json, rows), rows: normalizeRows(rows, "live") };
  }

  const raw = DEMO_ROWS;
  return {
    meta: { ...DEMO_META, totalSymbols: raw.length },
    rows: normalizeRows(raw, "demo"),
  };
}
