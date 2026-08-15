import { Link } from "@tanstack/react-router";
import type { FilterKey, StockRow } from "@/lib/scanner/types";
import { cn } from "@/lib/utils";

interface Props {
  rows: StockRow[];
}

interface CardDef {
  label: string;
  hint: string;
  value: number;
  filter: FilterKey;
  tone: string;
}

/** renderSummary(): 4 thẻ tổng hợp, bấm vào mở Danh sách với bộ lọc tương ứng. */
export function SummaryCards({ rows }: Props) {
  const cards: CardDef[] = [
    {
      label: "Cảnh báo sớm RVOL30",
      hint: "RVOL30 ≥ 200%",
      value: rows.filter((r) => r.signalRvol30_200pct).length,
      filter: "rvol30",
      tone: "border-early-border bg-early-soft text-early",
    },
    {
      label: "Đủ 4/4 tín hiệu",
      hint: "Tín hiệu rất mạnh",
      value: rows.filter((r) => r.signalCount === 4).length,
      filter: "4of4",
      tone: "border-signal4/25 bg-signal4-soft text-signal4",
    },
    {
      label: "Từ 3 tín hiệu trở lên",
      hint: "Bao gồm nhóm 4/4",
      value: rows.filter((r) => r.signalCount >= 3).length,
      filter: "3plus",
      tone: "border-signal3/30 bg-signal3-soft text-signal3",
    },
    {
      label: "Mã thiếu/lỗi dữ liệu",
      hint: "Cần kiểm tra nguồn",
      value: rows.filter((r) => r.hasMissingData).length,
      filter: "missing",
      tone: "border-border bg-surface text-muted-foreground",
    },
  ];

  return (
    <section aria-label="Tổng hợp" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {cards.map((c) => (
        <Link
          key={c.filter}
          to="/danh-sach"
          search={{ signal: c.filter }}
          className={cn(
            "rounded-xl border p-4 shadow-card transition-transform hover:-translate-y-0.5",
            c.tone,
          )}
        >
          <p className="text-xs font-semibold leading-snug">{c.label}</p>
          <p className="mt-2 text-3xl font-bold tabular">{c.value}</p>
          <p className="mt-1 text-[11px] opacity-70">{c.hint}</p>
        </Link>
      ))}
    </section>
  );
}
