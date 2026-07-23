import type { Cell } from "../api/types";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const LOW_CONFIDENCE = 70;

interface EditableTableProps {
  data: Cell[][];
  onChange: (rowIndex: number, colIndex: number, value: string) => void;
}

/** Renders an editable grid. Cells below the confidence threshold are highlighted. */
export function EditableTable({ data, onChange }: EditableTableProps) {
  if (data.length === 0) {
    return (
      <p className="rounded-lg bg-muted px-4 py-6 text-center text-sm text-muted-foreground">
        Aucune donnée structurée sur cette page.
      </p>
    );
  }

  const columnCount = Math.max(...data.map((row) => row.length));

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full border-collapse text-sm">
        <tbody>
          {data.map((row, r) => (
            <tr key={r}>
              {Array.from({ length: columnCount }).map((_, c) => {
                const cell = row[c] ?? { value: "", confidence: 0 };
                const low =
                  cell.value.trim() !== "" && cell.confidence < LOW_CONFIDENCE;
                const input = (
                  <input
                    value={cell.value}
                    onChange={(e) => onChange(r, c, e.target.value)}
                    className={`w-full min-w-[6rem] bg-transparent px-2 py-1.5 outline-none focus:bg-accent ${
                      low ? "text-amber-700 dark:text-amber-400" : "text-foreground"
                    }`}
                  />
                );
                return (
                  <td key={c} className={`border p-0 ${low ? "bg-amber-500/10" : ""}`}>
                    {cell.value ? (
                      <Tooltip>
                        <TooltipTrigger asChild>{input}</TooltipTrigger>
                        <TooltipContent>
                          {cell.confidence.toFixed(0)}% — {cell.value}
                        </TooltipContent>
                      </Tooltip>
                    ) : (
                      input
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
