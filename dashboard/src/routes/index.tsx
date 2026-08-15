import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { AppHeader } from "@/components/scanner/AppHeader";
import { StockCard } from "@/components/scanner/StockCard";
import { StockDetailDialog } from "@/components/scanner/StockDetailDialog";
import { SummaryCards } from "@/components/scanner/SummaryCards";
import { GROUPS } from "@/components/scanner/signal-meta";
import { applySorting } from "@/lib/scanner/filters";
import type { StockRow } from "@/lib/scanner/types";
import { useDashboard } from "@/lib/scanner/use-dashboard";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Tổng quan tín hiệu — VNStock Market Scanner" },
      {
        name: "description",
        content:
          "Bảng tổng quan quét tín hiệu cổ phiếu Việt Nam: giá ≥ 3%, khối lượng ≥ 200%, trên MA200 và cảnh báo dòng tiền sớm RVOL30.",
      },
      { property: "og:title", content: "Tổng quan tín hiệu — VNStock Market Scanner" },
      {
        property: "og:description",
        content: "Phát hiện nhanh cổ phiếu đáng chú ý theo 4 tín hiệu quét và RVOL30.",
      },
    ],
  }),
  component: OverviewPage,
});

const PREVIEW_LIMIT_1OF4 = 6;

function OverviewPage() {
  const { data, isFetching, refetch } = useDashboard();
  const [selected, setSelected] = useState<StockRow | null>(null);

  const rows = data?.rows ?? [];
  const early = applySorting(
    rows.filter((r) => r.signalRvol30_200pct),
    "rvol30",
  );

  return (
    <div className="min-h-screen bg-background">
      <AppHeader meta={data?.meta} onRefresh={() => void refetch()} refreshing={isFetching} />

      <main className="mx-auto max-w-7xl space-y-8 px-4 py-6 sm:px-6 sm:py-8">
        <SummaryCards rows={rows} />

        <section aria-labelledby="early-alert">
          <div className="mb-3">
            <h2 id="early-alert" className="text-base font-bold text-early sm:text-lg">
              Cảnh báo dòng tiền sớm
            </h2>
            <p className="text-xs text-muted-foreground">
              Mã có RVOL30 ≥ 200% — khối lượng 30 phút gần nhất vượt trung bình cùng khung giờ.
            </p>
          </div>
          {early.length === 0 ? (
            <EmptyBox text="Chưa có mã nào đạt RVOL30 ≥ 200%." />
          ) : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {early.map((row) => (
                <StockCard key={row.symbol} row={row} variant="early" onSelect={setSelected} />
              ))}
            </div>
          )}
        </section>

        {GROUPS.map((group) => {
          const groupRows = applySorting(
            rows.filter((r) => r.signalCount === group.count),
            "signal",
          );
          const limited =
            group.count === 1 ? groupRows.slice(0, PREVIEW_LIMIT_1OF4) : groupRows;

          return (
            <section key={group.count} aria-label={group.title}>
              <div className="mb-3 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
                <div className="min-w-0">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", group.accent)} />
                    <h2 className="truncate text-base font-bold sm:text-lg">{group.title}</h2>
                    <span
                      className={cn(
                        "shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-bold",
                        group.chip,
                      )}
                    >
                      {groupRows.length} mã
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">{group.subtitle}</p>
                </div>
                {group.count === 1 && groupRows.length > PREVIEW_LIMIT_1OF4 && (
                  <Link
                    to="/danh-sach"
                    search={{ signal: "exactly1" }}
                    className="shrink-0 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-semibold hover:bg-accent"
                  >
                    Xem tất cả
                  </Link>
                )}
              </div>

              {limited.length === 0 ? (
                <EmptyBox text="Không có mã nào trong nhóm này." />
              ) : (
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {limited.map((row) => (
                    <StockCard key={row.symbol} row={row} onSelect={setSelected} />
                  ))}
                </div>
              )}
            </section>
          );
        })}

        <p className="pb-4 text-center text-[11px] text-muted-foreground">
          Công cụ quét dữ liệu, không đưa ra khuyến nghị mua/bán.
        </p>
      </main>

      <StockDetailDialog row={selected} onOpenChange={(open) => !open && setSelected(null)} />
    </div>
  );
}

function EmptyBox({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-dashed border-border bg-card px-4 py-6 text-center text-sm text-muted-foreground">
      {text}
    </div>
  );
}
