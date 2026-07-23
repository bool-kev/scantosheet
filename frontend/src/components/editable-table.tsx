import { forwardRef, useLayoutEffect, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import { Plus, Trash2 } from "lucide-react";

import type { Cell } from "../api/types";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

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

/** A textarea that grows to fit its content — used only for the focused cell,
 * so long values can be read and edited without side-scrolling.
 *
 * Wrapped in forwardRef because it's rendered as TooltipTrigger's `asChild`
 * child: Radix needs a real ref to the DOM node to position the tooltip, and
 * a plain function component can't receive one under React 18. */
const AutoGrowTextarea = forwardRef<
  HTMLTextAreaElement,
  {
    value: string;
    onChange: (value: string) => void;
    onFocus: () => void;
    onBlur: () => void;
    className?: string;
  }
>(function AutoGrowTextarea({ value, onChange, onFocus, onBlur, className }, forwardedRef) {
  const innerRef = useRef<HTMLTextAreaElement | null>(null);

  useLayoutEffect(() => {
    const el = innerRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);

  return (
    <textarea
      ref={(node) => {
        innerRef.current = node;
        if (typeof forwardedRef === "function") forwardedRef(node);
        else if (forwardedRef) {
          (forwardedRef as MutableRefObject<HTMLTextAreaElement | null>).current = node;
        }
      }}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onFocus={onFocus}
      onBlur={onBlur}
      autoFocus
      rows={1}
      className={cn(
        "block w-full resize-none overflow-hidden whitespace-pre-wrap break-words bg-transparent px-2 py-1.5 outline-none",
        className,
      )}
    />
  );
});

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
  // Tracks which cell currently has real DOM focus, cleared on blur — this
  // drives the wrap-to-edit textarea, which should only appear while the
  // user is actually typing in that cell.
  const [focusedCell, setFocusedCell] = useState<ActiveCell | null>(null);

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
                    const isFocused = focusedCell?.row === r && focusedCell?.col === c;

                    const focus = () => {
                      setActiveCell({ row: r, col: c });
                      setFocusedCell({ row: r, col: c });
                    };
                    const blur = () =>
                      setFocusedCell((f) => (f?.row === r && f?.col === c ? null : f));

                    const colorClass = low ? "text-amber-700 dark:text-amber-400" : "text-foreground";
                    const field = isFocused ? (
                      <AutoGrowTextarea
                        value={cell.value}
                        onChange={(value) => onChange(r, c, value)}
                        onFocus={focus}
                        onBlur={blur}
                        className={colorClass}
                      />
                    ) : (
                      <input
                        value={cell.value}
                        onChange={(e) => onChange(r, c, e.target.value)}
                        onFocus={focus}
                        className={`w-full min-w-[6rem] bg-transparent px-2 py-1.5 outline-none focus:bg-accent ${colorClass}`}
                      />
                    );

                    return (
                      <td
                        key={c}
                        className={`border p-0 align-top ${low ? "bg-amber-500/10" : ""} ${
                          isActive ? "ring-1 ring-inset ring-ring" : ""
                        }`}
                      >
                        {/* The Tooltip/Trigger wrapper stays constant across renders so
                            typing the first character (value: "" -> non-empty) never
                            changes the tree shape around the field and remounts it. */}
                        <Tooltip>
                          <TooltipTrigger asChild>{field}</TooltipTrigger>
                          {cell.value && (
                            <TooltipContent>
                              {cell.confidence.toFixed(0)}%
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
