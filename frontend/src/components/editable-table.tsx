import type { Cell } from "../api/types";

const LOW_CONFIDENCE = 70;

interface EditableTableProps {
  data: Cell[][];
  onChange: (rowIndex: number, colIndex: number, value: string) => void;
}

/** Renders an editable grid. Cells below the confidence threshold are highlighted. */
export function EditableTable({ data, onChange }: EditableTableProps) {
  if (data.length === 0) {
    return (
      <p className="rounded-lg bg-slate-50 px-4 py-6 text-center text-sm text-slate-400">
        Aucune donnée structurée sur cette page.
      </p>
    );
  }

  const columnCount = Math.max(...data.map((row) => row.length));

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full border-collapse text-sm">
        <tbody>
          {data.map((row, r) => (
            <tr key={r}>
              {Array.from({ length: columnCount }).map((_, c) => {
                const cell = row[c] ?? { value: "", confidence: 0 };
                const low =
                  cell.value.trim() !== "" && cell.confidence < LOW_CONFIDENCE;
                return (
                  <td
                    key={c}
                    className={`border border-slate-200 p-0 ${
                      low ? "bg-amber-50" : ""
                    }`}
                    title={
                      cell.value ? `Confiance : ${cell.confidence.toFixed(0)}%` : undefined
                    }
                  >
                    <input
                      value={cell.value}
                      onChange={(e) => onChange(r, c, e.target.value)}
                      className={`w-full min-w-[6rem] bg-transparent px-2 py-1.5 outline-none focus:bg-brand-50 ${
                        low ? "text-amber-900" : "text-slate-700"
                      }`}
                    />
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
