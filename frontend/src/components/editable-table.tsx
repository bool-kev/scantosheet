import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";

import type { Cell } from "../api/types";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const LOW_CONFIDENCE = 70;

interface ActiveCell {
  row: number;
  col: number;
}

interface EditableTableProps {
  data: Cell[][];
  onChange: (rowIndex: number, colIndex: number, value: string) => void;
  /** `afterRow` is null to append at the end, or the row index to insert right after. */
  onAddRow: (afterRow: number | null) => void;
  /** `afterColumn` is null to append at the end, or the column index to insert right after. */
  onAddColumn: (afterColumn: number | null) => void;
  onDeleteRow: (row: number) => void;
  onDeleteColumn: (col: number) => void;
}

/** Renders an editable grid. Cells below the confidence threshold are highlighted. */
export function EditableTable({
  data,
  onChange,
  onAddRow,
  onAddColumn,
  onDeleteRow,
  onDeleteColumn,
}: EditableTableProps) {
  const columnCount = Math.max(0, ...data.map((row) => row.length));
  // Tracks the last focused cell so "Ajouter"/"Supprimer" act on it instead of
  // always appending at the end. Only set on focus (never cleared on blur):
  // clicking a button below blurs the input first, and clearing here would
  // erase the position right before the click handler needs to read it.
  const [activeCell, setActiveCell] = useState<ActiveCell | null>(null);

  const canDeleteColumn = activeCell !== null && columnCount > 1;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onAddRow(activeCell ? activeCell.row : null)}
        >
          <Plus />
          {activeCell ? `Insérer une ligne (après la ${activeCell.row + 1})` : "Ajouter une ligne"}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onAddColumn(activeCell ? activeCell.col : null)}
          disabled={data.length === 0}
        >
          <Plus />
          {activeCell
            ? `Insérer une colonne (après la ${activeCell.col + 1})`
            : "Ajouter une colonne"}
        </Button>

        <span className="mx-1 h-4 w-px bg-border" aria-hidden="true" />

        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!activeCell}
          onClick={() => {
            if (!activeCell) return;
            onDeleteRow(activeCell.row);
            setActiveCell(null);
          }}
          className="text-destructive hover:bg-destructive/10 hover:text-destructive"
        >
          <Trash2 /> Supprimer la ligne{activeCell ? ` (${activeCell.row + 1})` : ""}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!canDeleteColumn}
          onClick={() => {
            if (!activeCell) return;
            onDeleteColumn(activeCell.col);
            setActiveCell(null);
          }}
          className="text-destructive hover:bg-destructive/10 hover:text-destructive"
        >
          <Trash2 /> Supprimer la colonne{activeCell ? ` (${activeCell.col + 1})` : ""}
        </Button>
      </div>

      {!activeCell && data.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Cliquez dans une cellule pour insérer ou supprimer à cet endroit précis.
        </p>
      )}

      {data.length === 0 ? (
        <p className="rounded-lg bg-muted px-4 py-6 text-center text-sm text-muted-foreground">
          Aucune donnée structurée sur cette page. Ajoutez une ligne pour commencer.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full border-collapse text-sm">
            <tbody>
              {data.map((row, r) => (
                <tr key={r}>
                  {Array.from({ length: columnCount }).map((_, c) => {
                    const cell = row[c] ?? { value: "", confidence: 0 };
                    const low =
                      cell.value.trim() !== "" && cell.confidence < LOW_CONFIDENCE;
                    const isActive = activeCell?.row === r && activeCell?.col === c;
                    const input = (
                      <input
                        value={cell.value}
                        onChange={(e) => onChange(r, c, e.target.value)}
                        onFocus={() => setActiveCell({ row: r, col: c })}
                        className={`w-full min-w-[6rem] bg-transparent px-2 py-1.5 outline-none focus:bg-accent ${
                          low ? "text-amber-700 dark:text-amber-400" : "text-foreground"
                        }`}
                      />
                    );
                    return (
                      <td
                        key={c}
                        className={`border p-0 ${low ? "bg-amber-500/10" : ""} ${
                          isActive ? "ring-1 ring-inset ring-ring" : ""
                        }`}
                      >
                        {/* The Tooltip/Trigger wrapper stays constant across renders so
                            typing the first character (value: "" -> non-empty) never
                            changes the tree shape around `input` and remounts it. */}
                        <Tooltip>
                          <TooltipTrigger asChild>{input}</TooltipTrigger>
                          {cell.value && (
                            <TooltipContent>
                              {cell.confidence.toFixed(0)}% — {cell.value}
                            </TooltipContent>
                          )}
                        </Tooltip>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
