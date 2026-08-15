import type { StockRow } from "@/lib/scanner/types";

export interface GroupMeta {
  count: 1 | 2 | 3 | 4;
  title: string;
  subtitle: string;
  /** class nền nhạt + viền + chữ cho nhãn nhóm */
  chip: string;
  accent: string;
  cardBorder: string;
}

export const GROUPS: GroupMeta[] = [
  {
    count: 4,
    title: "4/4 — Tín hiệu rất mạnh",
    subtitle: "Hội tụ đủ 4 điều kiện quét",
    chip: "bg-signal4-soft text-signal4 border-signal4/25",
    accent: "bg-signal4",
    cardBorder: "border-signal4/25",
  },
  {
    count: 3,
    title: "3/4 — Tín hiệu mạnh",
    subtitle: "Thiếu một điều kiện",
    chip: "bg-signal3-soft text-signal3 border-signal3/30",
    accent: "bg-signal3",
    cardBorder: "border-signal3/25",
  },
  {
    count: 2,
    title: "2/4 — Đang hình thành",
    subtitle: "Cần theo dõi thêm",
    chip: "bg-signal2-soft text-signal2 border-signal2/30",
    accent: "bg-signal2",
    cardBorder: "border-signal2/25",
  },
  {
    count: 1,
    title: "1/4 — Tín hiệu ban đầu",
    subtitle: "Mới xuất hiện một điều kiện",
    chip: "bg-signal1-soft text-signal1 border-signal1/25",
    accent: "bg-signal1",
    cardBorder: "border-signal1/20",
  },
];

export function groupOf(count: number): GroupMeta {
  return GROUPS.find((g) => g.count === count) ?? GROUPS[3]!;
}

export const SIGNAL_LABELS = {
  price: "Giá ≥ 3%",
  volume: "KL ngày ≥ 200%",
  ma200: "Trên MA200",
  rvol30: "RVOL30 ≥ 200%",
} as const;

export function signalFlags(row: StockRow) {
  return [
    { label: SIGNAL_LABELS.price, active: row.signalPrice3pct },
    { label: SIGNAL_LABELS.volume, active: row.signalVolume200pct },
    { label: SIGNAL_LABELS.ma200, active: row.signalAboveMa200 },
    { label: SIGNAL_LABELS.rvol30, active: row.signalRvol30_200pct },
  ];
}
