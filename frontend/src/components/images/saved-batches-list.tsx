import type { ImageBatchSummary } from "../../api/types";
import { useBatches, useDeleteBatch } from "../../hooks/useImagePdf";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface SavedBatchesListProps {
  onOpen: (batch: ImageBatchSummary) => void;
}

export function SavedBatchesList({ onOpen }: SavedBatchesListProps) {
  const { data, isLoading, isError } = useBatches();
  const deleteBatch = useDeleteBatch();

  if (isLoading) {
    return <p className="py-6 text-center text-sm text-slate-400">Chargement…</p>;
  }
  if (isError) {
    return (
      <p className="py-6 text-center text-sm text-red-600">
        Impossible de charger les lots enregistrés.
      </p>
    );
  }

  const batches = data ?? [];
  if (batches.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-slate-400">
        Aucun lot enregistré pour le moment.
      </p>
    );
  }

  const onDelete = (batch: ImageBatchSummary) => {
    if (window.confirm(`Supprimer le lot « ${batch.name} » ?`)) {
      deleteBatch.mutate(batch.id);
    }
  };

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3 font-medium">Nom</th>
            <th className="px-4 py-3 font-medium">Images</th>
            <th className="px-4 py-3 font-medium">Dernière modification</th>
            <th className="px-4 py-3 text-right font-medium">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {batches.map((batch) => (
            <tr key={batch.id} className="hover:bg-slate-50">
              <td className="max-w-xs truncate px-4 py-3 font-medium text-slate-700">
                {batch.name}
              </td>
              <td className="px-4 py-3 text-slate-500">{batch.image_count}</td>
              <td className="px-4 py-3 text-slate-500">{formatDate(batch.updated_at)}</td>
              <td className="px-4 py-3">
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => onOpen(batch)}
                    className="rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-600"
                  >
                    Ouvrir
                  </button>
                  <button
                    onClick={() => onDelete(batch)}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100"
                  >
                    Supprimer
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
