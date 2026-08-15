import { Link } from "@tanstack/react-router";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DashboardMeta } from "@/lib/scanner/types";
import { cn } from "@/lib/utils";

interface Props {
  meta?: DashboardMeta | undefined;
  onRefresh: () => void;
  refreshing?: boolean;
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="truncate text-sm font-semibold tabular">{value}</p>
    </div>
  );
}

export function AppHeader({ meta, onRefresh, refreshing }: Props) {
  const isDemo = meta?.mode !== "LIVE";

  return (
    <header className="border-b border-border bg-card">
      <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 sm:py-5">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-lg font-bold tracking-tight sm:text-xl">
              VNStock Market Scanner
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold",
                  meta?.systemStatus === "OK"
                    ? "border-up/25 bg-up/10 text-up"
                    : "border-destructive/25 bg-destructive/10 text-destructive",
                )}
              >
                <span className="h-1.5 w-1.5 rounded-full bg-current" />
                {meta?.systemStatus === "OK" ? "Hệ thống hoạt động" : "Hệ thống có sự cố"}
              </span>
              <span
                className={cn(
                  "rounded-full border px-2 py-0.5 text-[11px] font-bold tracking-wide",
                  isDemo
                    ? "border-signal2/30 bg-signal2-soft text-signal2"
                    : "border-up/25 bg-up/10 text-up",
                )}
              >
                {isDemo ? "DEMO" : "LIVE"}
              </span>
            </div>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            className="shrink-0 gap-2"
            aria-label="Làm mới dữ liệu"
          >
            <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
            <span className="hidden sm:inline">Làm mới</span>
          </Button>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 rounded-xl bg-surface p-3 sm:grid-cols-4">
          <MetaItem label="Dữ liệu thị trường" value={meta?.marketUpdatedAt ?? "—"} />
          <MetaItem label="Dashboard kiểm tra" value={meta?.dashboardCheckedAt ?? "—"} />
          <MetaItem label="Tổng mã theo dõi" value={String(meta?.totalSymbols ?? "—")} />
          <MetaItem label="Nguồn dữ liệu" value={meta?.dataSource ?? "—"} />
        </div>

        {isDemo && (
          <p className="mt-3 rounded-lg border border-signal2/30 bg-signal2-soft px-3 py-2 text-xs font-semibold text-signal2">
            DEMO DATA – Không phải dữ liệu thị trường thật.
          </p>
        )}

        <nav className="mt-4 flex gap-1 rounded-xl bg-surface p-1" aria-label="Điều hướng chính">
          <Link
            to="/"
            className="flex-1 rounded-lg px-3 py-2 text-center text-sm font-semibold text-muted-foreground transition-colors hover:text-foreground"
            activeOptions={{ exact: true }}
            activeProps={{ className: "bg-card text-foreground shadow-card" }}
          >
            Tổng quan
          </Link>
          <Link
            to="/danh-sach"
            className="flex-1 rounded-lg px-3 py-2 text-center text-sm font-semibold text-muted-foreground transition-colors hover:text-foreground"
            activeProps={{ className: "bg-card text-foreground shadow-card" }}
          >
            Danh sách cổ phiếu
          </Link>
        </nav>
      </div>
    </header>
  );
}
