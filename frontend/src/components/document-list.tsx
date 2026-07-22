import { Link } from "react-router-dom";

import type { DocumentSummary } from "../api/types";
import { useDeleteDocument, useDocuments } from "../hooks/useDocuments";
import { StatusBadge } from "./status-badge";

function formatDate(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function DocumentList() {
  const { data, isLoading, isError, error } = useDocuments();
  const deleteDoc = useDeleteDocument();

  if (isLoading) {
    return <p className="py-8 text-center text-sm text-slate-400">Chargement…</p>;
  }
  if (isError) {
    return (
      <p className="py-8 text-center text-sm text-red-600">
        Impossible de charger les documents : {(error as Error).message}
      </p>
    );
  }

  const documents = data?.items ?? [];
  if (documents.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-slate-400">
        Aucun document pour le moment. Envoyez un PDF pour commencer.
      </p>
    );
  }

  const onDelete = (doc: DocumentSummary) => {
    if (window.confirm(`Supprimer « ${doc.filename} » ?`)) {
      deleteDoc.mutate(doc.id);
    }
  };

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3 font-medium">Fichier</th>
            <th className="px-4 py-3 font-medium">Pages</th>
            <th className="px-4 py-3 font-medium">Statut</th>
            <th className="px-4 py-3 font-medium">Date</th>
            <th className="px-4 py-3 text-right font-medium">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {documents.map((doc) => (
            <tr key={doc.id} className="hover:bg-slate-50">
              <td className="max-w-xs truncate px-4 py-3 font-medium text-slate-700">
                {doc.filename}
              </td>
              <td className="px-4 py-3 text-slate-500">{doc.page_count}</td>
              <td className="px-4 py-3">
                <StatusBadge status={doc.status} />
                {doc.status === "error" && doc.error_message && (
                  <span className="ml-2 text-xs text-red-500" title={doc.error_message}>
                    ⚠
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-slate-500">{formatDate(doc.created_at)}</td>
              <td className="px-4 py-3">
                <div className="flex justify-end gap-2">
                  {doc.status === "done" && (
                    <Link
                      to={`/documents/${doc.id}`}
                      className="rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-600"
                    >
                      Aperçu
                    </Link>
                  )}
                  <button
                    onClick={() => onDelete(doc)}
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
