import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { AppHeader } from "@/components/scanner/AppHeader";
import { StockCard } from "@/components/scanner/StockCard";
import { StockDetailDialog } from "@/components/scanner/StockDetailDialog";
import { StockTable } from "@/components/scanner/StockTable";
import { Input } from "@/components/ui/input";
import {
  applyFilters,
  applySorting,
  EXCHANGE_FILTERS,
  SIGNAL_FILTERS,
  SORT_OPTIONS,
} from "@/lib/scanner/filters";
import type { FilterKey, SortKey, StockRow } from "@/lib/scanner/types";
import { useDashboard } from "@/lib/scanner/use-dashboard";
import { cn } from "@/lib/utils";

interface ListSearch {
  signal?: FilterKey;
}

export const Route = createFileRoute("/danh-sach")({
  validateSearch: (search: Record<string, unknown>): ListSearch =>
    typeof search['signal'] === "string" ? { signal: search['signal'] as FilterKey } : {},
  head: () => ({
    meta: [
      { title: "Danh sách cổ phiếu — VNStock Market Scanner" },
      {
        name: "description",
        content:
          "Tra cứu, lọc và sắp xếp toàn bộ mã theo dõi theo tín hiệu giá, khối lượng, MA200 và RVOL30.",
      },
      { property: "og:title", content: "Danh sách cổ phiếu — VNStock Market Scanner" },
      {
        property: "og:description",
        content: "Bộ lọc và bảng dữ liệu đầy đủ cho toàn bộ mã đang theo dõi.",
      },
    ],
  }),
  component: StockListPage,
});

function Chip({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border bg-card text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function StockListPage() {
  const { data, isFetching, refetch } = useDashboard();
  const navigate = useNavigate({ from: "/danh-sach" });
  const { signal } = Route.useSearch();

  const [search, setSearch] = useState("");
  const [exchange, setExchange] = useState<FilterKey>("all");
  const [sort, setSort] = useState<SortKey>("signal");
  const [selected, setSelected] = useState<StockRow | null>(null);

  const rows = data?.rows ?? [];

  const visible = useMemo(
    () =>
      applySorting(
        applyFilters(rows, { search, exchange, signal: signal ?? null }),
        sort,
      ),
    [rows, search, exchange, signal, sort],
  );

  const setSignal = (key: FilterKey | null) =>
    void navigate({ search: key ? { signal: key } : {} });

  return (
    <div className="min-h-screen bg-background">
      <AppHeader meta={data?.meta} onRefresh={() => void refetch()} refreshing={isFetching} />

      <main className="mx-auto max-w-7xl space-y-5 px-4 py-6 sm:px-6 sm:py-8">
        <div className="rounded-xl border border-border bg-card p-4 shadow-card">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Tìm theo mã cổ phiếu…"
              className="pl-9"
              aria-label="Tìm theo mã cổ phiếu"
            />
          </div>

          <div className="mt-4 space-y-3">
            <div>
              <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                Sàn giao dịch
              </p>
              <div className="flex flex-wrap gap-2">
                {EXCHANGE_FILTERS.map((f) => (
                  <Chip
                    key={f.key}
                    active={exchange === f.key}
                    onClick={() => setExchange(f.key)}
                  >
                    {f.label}
                  </Chip>
                ))}
              </div>
            </div>

            <div>
              <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                Bộ lọc tín hiệu
              </p>
              <div className="flex flex-wrap gap-2">
                <Chip active={!signal} onClick={() => setSignal(null)}>
                  Tất cả tín hiệu
                </Chip>
                {SIGNAL_FILTERS.map((f) => (
                  <Chip key={f.key} active={signal === f.key} onClick={() => setSignal(f.key)}>
                    {f.label}
                  </Chip>
                ))}
              </div>
            </div>

            <div>
              <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                Sắp xếp
              </p>
              <div className="flex flex-wrap gap-2">
                {SORT_OPTIONS.map((o) => (
                  <Chip key={o.key} active={sort === o.key} onClick={() => setSort(o.key)}>
                    {o.label}
                  </Chip>
                ))}
              </div>
            </div>
          </div>
        </div>

        <p className="text-xs text-muted-foreground">
          Hiển thị <span className="font-semibold text-foreground">{visible.length}</span> /{" "}
          {rows.length} mã theo dõi.
        </p>

        {visible.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-card px-4 py-10 text-center text-sm text-muted-foreground">
            Không tìm thấy mã phù hợp với bộ lọc hiện tại.
          </div>
        ) : (
          <>
            <div className="hidden lg:block">
              <StockTable rows={visible} onSelect={setSelected} />
            </div>
            <div className="grid gap-3 lg:hidden">
              {visible.map((row) => (
                <StockCard key={row.symbol} row={row} onSelect={setSelected} />
              ))}
            </div>
          </>
        )}

        <p className="pb-4 text-center text-[11px] text-muted-foreground">
          Công cụ quét dữ liệu, không đưa ra khuyến nghị mua/bán.
        </p>
      </main>

      <StockDetailDialog row={selected} onOpenChange={(open) => !open && setSelected(null)} />
    </div>
  );
}
