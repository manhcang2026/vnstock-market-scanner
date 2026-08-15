import type { StockRow } from "@/lib/scanner/types";
import {
  EMPTY,
  formatPercent,
  formatPrice,
  formatRatioPercent,
  formatSessions,
} from "@/lib/scanner/format";
import { cn } from "@/lib/utils";
import { groupOf, signalFlags } from "./signal-meta";

interface Props {
  row: StockRow;
  variant?: "group" | "early";
  onSelect: (row: StockRow) => void;
}

export function changeTone(value: number | null): string {
  if (value === null) return "text-muted-foreground";
  if (value > 0) return "text-up";
  if (value < 0) return "text-down";
  return "text-neutral";
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string | undefined }) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn("text-sm font-semibold leading-tight tabular", tone)}>{value}</p>
    </div>
  );
}

export function rvol30Display(row: StockRow): string {
  if (row.rvol30Sessions === 0) return "Chưa đủ dữ liệu";
  if (row.rvol30Pct === null) return "Chưa có dữ liệu";
  return formatRatioPercent(row.rvol30Pct);
}

/** renderStockCard() */
export function StockCard({ row, variant = "group", onSelect }: Props) {
  const group = groupOf(row.signalCount);
  const isEarly = variant === "early";
  const flags = signalFlags(row);

  return (
    <button
      type="button"
      onClick={() => onSelect(row)}
      className={cn(
        "w-full rounded-xl border bg-card p-4 text-left shadow-card transition-colors hover:border-foreground/20",
        isEarly ? "border-early-border bg-early-soft/60" : group.cardBorder,
      )}
    >
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-base font-bold tracking-tight">{row.symbol}</span>
            <span className="shrink-0 rounded border border-border bg-surface px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
              {row.exchange}
            </span>
          </div>
          <p className="mt-1 text-sm tabular text-muted-foreground">
            {formatPrice(row.currentPrice)}{" "}
            <span className={cn("font-semibold", changeTone(row.changePct))}>
              {formatPercent(row.changePct)}
            </span>
          </p>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-bold",
            isEarly ? "border-early-border bg-card text-early" : group.chip,
          )}
        >
          {row.signalCount}/4
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label="KL ngày" value={formatRatioPercent(row.dayVolumeRatioPct)} />
        <Metric
          label="Cách MA200"
          value={formatPercent(row.ma200DistancePct)}
          tone={changeTone(row.ma200DistancePct)}
        />
        <Metric
          label="RVOL30"
          value={rvol30Display(row)}
          tone={row.signalRvol30_200pct ? "text-early" : undefined}
        />
        <Metric label="Phiên RVOL30" value={formatSessions(row.rvol30Sessions)} />
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {flags.map((f) => (
          <span
            key={f.label}
            className={cn(
              "rounded-md border px-1.5 py-0.5 text-[10px] font-medium",
              f.active
                ? "border-foreground/15 bg-foreground/5 text-foreground"
                : "border-border bg-surface text-muted-foreground/60 line-through",
            )}
          >
            {f.label}
          </span>
        ))}
      </div>

      {row.hasMissingData && (
        <p className="mt-2 text-[11px] font-medium text-muted-foreground">
          {row.note ?? "Thiếu dữ liệu"} {EMPTY}
        </p>
      )}
    </button>
  );
}
