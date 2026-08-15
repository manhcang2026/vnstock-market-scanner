import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { StockRow } from "@/lib/scanner/types";
import {
  formatDataStatus,
  formatPercent,
  formatPrice,
  formatRatioPercent,
  formatSessions,
  formatVolume,
} from "@/lib/scanner/format";

import { cn } from "@/lib/utils";
import { changeTone, rvol30Display } from "./StockCard";
import { groupOf, signalFlags } from "./signal-meta";

interface Props {
  row: StockRow | null;
  onOpenChange: (open: boolean) => void;
}

function Line({ label, value, tone }: { label: string; value: string; tone?: string | undefined }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/60 py-2 last:border-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn("text-sm font-semibold tabular text-right", tone)}>{value}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <p className="mb-1 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      {children}
    </div>
  );
}

/** renderStockDetail() */
export function StockDetailDialog({ row, onOpenChange }: Props) {
  return (
    <Dialog open={row !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        {row && (
          <>
            <DialogHeader>
              <DialogTitle className="flex flex-wrap items-center gap-2">
                <span className="text-xl font-bold">{row.symbol}</span>
                <span className="rounded border border-border bg-surface px-1.5 py-0.5 text-[11px] font-semibold text-muted-foreground">
                  {row.exchange}
                </span>
                <span
                  className={cn(
                    "rounded-full border px-2 py-0.5 text-[11px] font-bold",
                    groupOf(row.signalCount).chip,
                  )}
                >
                  {row.signalCount}/4 tín hiệu
                </span>
              </DialogTitle>
              <DialogDescription>
                Chi tiết dữ liệu quét — chỉ mang tính thông tin, không phải khuyến nghị đầu tư.
              </DialogDescription>
            </DialogHeader>

            <div className="grid gap-3">
              <div className="flex flex-wrap gap-1.5">
                {signalFlags(row).map((f) => (
                  <span
                    key={f.label}
                    className={cn(
                      "rounded-md border px-2 py-0.5 text-[11px] font-medium",
                      f.active
                        ? "border-foreground/15 bg-foreground/5 text-foreground"
                        : "border-border bg-surface text-muted-foreground/60 line-through",
                    )}
                  >
                    {f.label}
                  </span>
                ))}
              </div>

              <Section title="Giá">
                <Line label="Giá hiện tại" value={formatPrice(row.currentPrice)} />
                <Line label="Giá đóng cửa gần nhất" value={formatPrice(row.prevClose)} />
                <Line
                  label="% thay đổi"
                  value={formatPercent(row.changePct)}
                  tone={changeTone(row.changePct)}
                />
                <Line label="MA200" value={formatPrice(row.ma200)} />
                <Line
                  label="Khoảng cách MA200"
                  value={formatPercent(row.ma200DistancePct)}
                  tone={changeTone(row.ma200DistancePct)}
                />
                <Line label="Số phiên MA200" value={formatSessions(row.ma200Sessions, 200)} />
              </Section>

              <Section title="Khối lượng ngày">
                <Line label="KL tích lũy" value={formatVolume(row.cumVolume)} />
                <Line label="KLTB10 phiên" value={formatVolume(row.avgVolume10)} />
                <Line
                  label="Số phiên KLTB10"
                  value={formatSessions(row.avgVolume10Sessions, 10)}
                />
                <Line label="Tỷ lệ KL ngày" value={formatRatioPercent(row.dayVolumeRatioPct)} />
              </Section>

              <Section title="Cảnh báo sớm RVOL30">
                <Line label="KL 30 phút gần nhất" value={formatVolume(row.volume30m)} />
                <Line
                  label="KL30 trung bình cùng khung"
                  value={
                    row.rvol30Sessions === 0
                      ? "Chưa đủ dữ liệu"
                      : formatVolume(row.avgVolume30mSameSlot)
                  }
                />
                <Line
                  label="RVOL30"
                  value={rvol30Display(row)}
                  tone={row.signalRvol30_200pct ? "text-early" : undefined}
                />
                <Line label="Số phiên RVOL30" value={formatSessions(row.rvol30Sessions, 10)} />
              </Section>

              <Section title="Thông tin dữ liệu">
                <Line label="Ngày giao dịch" value={row.tradingDate} />
                <Line label="Khung thời gian" value={row.timeSlot} />
                <Line label="Cập nhật lúc" value={row.updatedAt} />
                <Line
                  label="Trạng thái dữ liệu"
                  value={row.hasMissingData ? "Thiếu dữ liệu" : "Đầy đủ"}
                />
                <Line label="Nguồn dữ liệu" value={row.dataSource} />
                <Line label="Nhãn" value={formatDataStatus(row.dataStatus)} />

              </Section>

              {row.note && (
                <p className="rounded-lg border border-border bg-surface px-3 py-2 text-xs text-muted-foreground">
                  Ghi chú: {row.note}
                </p>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
