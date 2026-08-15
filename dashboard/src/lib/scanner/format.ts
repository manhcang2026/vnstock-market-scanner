// Hàm định dạng hiển thị (tiếng Việt).

export const EMPTY = "—";

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  return value.toLocaleString("vi-VN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatPrice(value: number | null | undefined): string {
  return formatNumber(value, 2);
}

export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value, digits)}%`;
}

export function formatRatioPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  return `${formatNumber(value, digits)}%`;
}

export function formatVolume(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  if (value >= 1_000_000) return `${formatNumber(value / 1_000_000, 2)} triệu`;
  if (value >= 1_000) return `${formatNumber(value / 1_000, 1)} nghìn`;
  return formatNumber(value, 0);
}

export function formatSessions(value: number | null | undefined, total = 10): string {
  if (value === null || value === undefined) return EMPTY;
  return `${value}/${total}`;
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** Ngày giao dịch: ISO / Date Apps Script / dd/MM/yyyy -> dd/MM/yyyy */
export function formatTradingDate(value: string | Date | null | undefined): string {
  if (!value) return EMPTY;
  if (typeof value === "string" && /^\d{2}\/\d{2}\/\d{4}$/.test(value.trim())) return value.trim();
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return typeof value === "string" ? value : EMPTY;
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
}

function timePart(value: string): string {
  const trimmed = value.trim();
  const direct = trimmed.match(/^(\d{1,2}):(\d{2})/);
  if (direct?.[1] && direct[2]) return `${pad(Number(direct[1]))}:${direct[2]}`;
  const d = new Date(trimmed); // xử lý chuỗi Date 1899 từ Apps Script
  if (!Number.isNaN(d.getTime())) return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return trimmed;
}

/** Khung thời gian: "HH:mm-HH:mm", "HH:mm" hoặc chuỗi Date 1899 -> chỉ hiển thị HH:mm */
export function formatTimeSlot(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const parts = String(value).split(/\s*[-–—~]\s*/).filter(Boolean);
  if (parts.length >= 2 && parts[0] && parts[1]) {
    return `${timePart(parts[0])}–${timePart(parts[1])}`;
  }
  return timePart(String(value));
}

/** Cập nhật lúc: chỉ hiển thị HH:mm:ss (bỏ ISO dài / ngày 1899). */
export function formatUpdatedAt(value: string | Date | null | undefined): string {
  if (!value) return EMPTY;
  if (typeof value === "string" && /^\d{1,2}:\d{2}(:\d{2})?$/.test(value.trim())) {
    return value.trim();
  }
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return typeof value === "string" ? value : EMPTY;
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

const DATA_STATUS_LABELS: Record<string, string> = {
  DEMO: "DEMO – dữ liệu mẫu",
  OK: "OK – dữ liệu thị trường",
  OUT_OF_SESSION_TEST: "Ngoài giờ - dữ liệu kiểm tra",
  MISSING_MARKET_DATA: "Thiếu dữ liệu thị trường",
};

export function formatDataStatus(value: string | null | undefined): string {
  if (!value) return EMPTY;
  return DATA_STATUS_LABELS[value] ?? value;
}

