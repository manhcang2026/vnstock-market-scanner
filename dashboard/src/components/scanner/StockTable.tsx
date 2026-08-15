import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { StockRow } from "@/lib/scanner/types";
import {
  formatDataStatus,
  formatPercent,
  formatPrice,
  formatRatioPercent,
  formatSessions,
} from "@/lib/scanner/format";
import { cn } from "@/lib/utils";
import { changeTone, rvol30Display } from "./StockCard";
import { groupOf } from "./signal-meta";

interface Props {
  rows: StockRow[];
  onSelect: (row: StockRow) => void;
}

export function StockTable({ rows, onSelect }: Props) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card shadow-card">
      <Table>
        <TableHeader>
          <TableRow className="bg-surface">
            <TableHead>Mã</TableHead>
            <TableHead>Sàn</TableHead>
            <TableHead className="text-right">Giá</TableHead>
            <TableHead className="text-right">% thay đổi</TableHead>
            <TableHead className="text-right">KL ngày</TableHead>
            <TableHead className="text-right">MA200</TableHead>
            <TableHead className="text-right">RVOL30</TableHead>
            <TableHead className="text-right">Phiên RVOL30</TableHead>
            <TableHead className="text-center">Tín hiệu</TableHead>
            <TableHead>Trạng thái dữ liệu</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow
              key={row.symbol}
              onClick={() => onSelect(row)}
              className="cursor-pointer"
              tabIndex={0}
            >
              <TableCell className="font-bold">{row.symbol}</TableCell>
              <TableCell className="text-muted-foreground">{row.exchange}</TableCell>
              <TableCell className="text-right tabular">{formatPrice(row.currentPrice)}</TableCell>
              <TableCell className={cn("text-right tabular font-semibold", changeTone(row.changePct))}>
                {formatPercent(row.changePct)}
              </TableCell>
              <TableCell className="text-right tabular">
                {formatRatioPercent(row.dayVolumeRatioPct)}
              </TableCell>
              <TableCell
                className={cn("text-right tabular", changeTone(row.ma200DistancePct))}
              >
                {formatPercent(row.ma200DistancePct)}
              </TableCell>
              <TableCell
                className={cn(
                  "text-right tabular",
                  row.signalRvol30_200pct && "font-semibold text-early",
                )}
              >
                {rvol30Display(row)}
              </TableCell>
              <TableCell className="text-right tabular text-muted-foreground">
                {formatSessions(row.rvol30Sessions)}
              </TableCell>
              <TableCell className="text-center">
                <span
                  className={cn(
                    "inline-block rounded-full border px-2 py-0.5 text-[11px] font-bold",
                    groupOf(row.signalCount).chip,
                  )}
                >
                  {row.signalCount}/4
                </span>
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {row.dataStatus === "OUT_OF_SESSION_TEST"
                  ? formatDataStatus(row.dataStatus)
                  : row.hasMissingData
                    ? "Thiếu dữ liệu"
                    : "Đầy đủ"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
