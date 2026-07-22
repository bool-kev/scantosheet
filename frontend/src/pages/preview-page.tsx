import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, api } from "../api/client";
import type { Cell, PageData } from "../api/types";
import { EditableTable } from "../components/editable-table";
import { StatusBadge } from "../components/status-badge";
import { useDocument, useUpdateData } from "../hooks/useDocuments";

export function PreviewPage() {
  const { id } = useParams<{ id: string }>();
  const documentId = Number(id);
  const { data: doc, isLoading, isError, error } = useDocument(documentId);
  const updateData = useUpdateData(documentId);

  const [pages, setPages] = useState<PageData[]>([]);
  const [activePage, setActivePage] = useState(0);
  const [merge, setMerge] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // Sync local editable copy whenever the fetched document changes.
  useEffect(() => {
    if (doc?.pages) {
      setPages(doc.pages);
      setDirty(false);
    }
  }, [doc?.id, doc?.pages]);

  // Seed the export layout from the choice made at upload time.
  useEffect(() => {
    if (doc) {
      setMerge(doc.merge_pages);
    }
  }, [doc?.id, doc?.merge_pages]);

  if (isLoading) {
    return <p className="p-10 text-center text-slate-400">Chargement…</p>;
  }
  if (isError || !doc) {
    return (
      <div className="p-10 text-center text-red-600">
        {(error as Error)?.message ?? "Document introuvable"}
        <div className="mt-4">
          <Link to="/" className="text-brand-600 underline">
            Retour
          </Link>
        </div>
      </div>
    );
  }

  const handleCellChange = (rowIndex: number, colIndex: number, value: string) => {
    setPages((prev) => {
      const next = prev.map((p) => ({ ...p, data: p.data.map((row) => [...row]) }));
      const page = next[activePage];
      while (page.data[rowIndex].length <= colIndex) {
        page.data[rowIndex].push({ value: "", confidence: 100 });
      }
      const existing = page.data[rowIndex][colIndex];
      page.data[rowIndex][colIndex] = { value, confidence: existing?.confidence ?? 100 };
      return next;
    });
    setDirty(true);
    setSaved(false);
  };

  const handleSave = () => {
    const payload = pages.map((p) => ({
      page_number: p.page_number,
      data: p.data as Cell[][],
    }));
    updateData.mutate(payload, {
      onSuccess: () => {
        setDirty(false);
        setSaved(true);
      },
    });
  };

  // Downloads go through fetch (not a plain link) so the API key header travels
  // with the request.
  const handleDownload = async (fmt: "xlsx" | "csv") => {
    setDownloadError(null);
    try {
      await api.download(doc.id, fmt, fmt === "xlsx" ? merge : false);
    } catch (err) {
      setDownloadError(
        err instanceof ApiError ? err.message : "Échec du téléchargement",
      );
    }
  };

  const current = pages[activePage];

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <Link to="/" className="text-sm text-brand-600 hover:underline">
            ← Retour à l'historique
          </Link>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">{doc.filename}</h1>
          <div className="mt-1 flex items-center gap-3 text-sm text-slate-500">
            <StatusBadge status={doc.status} />
            <span>{doc.page_count} page(s)</span>
            <span>Langue : {doc.language}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={merge}
              onChange={(e) => setMerge(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            Fusionner les pages
          </label>
          <button
            onClick={handleSave}
            disabled={!dirty || updateData.isPending}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 disabled:opacity-40 hover:bg-slate-100"
          >
            {updateData.isPending ? "Enregistrement…" : "Enregistrer"}
          </button>
          <button
            onClick={() => handleDownload("xlsx")}
            className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700"
          >
            Excel (.xlsx)
          </button>
          <button
            onClick={() => handleDownload("csv")}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            CSV
          </button>
        </div>
      </div>

      {downloadError && (
        <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {downloadError}
        </p>
      )}
      {saved && (
        <p className="mb-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          Modifications enregistrées.
        </p>
      )}
      {dirty && (
        <p className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">
          Modifications non enregistrées — pensez à enregistrer avant de télécharger.
        </p>
      )}

      {pages.length > 1 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {pages.map((p, index) => (
            <button
              key={p.page_number}
              onClick={() => setActivePage(index)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                index === activePage
                  ? "bg-brand-500 text-white"
                  : "border border-slate-200 text-slate-600 hover:bg-slate-100"
              }`}
            >
              Page {p.page_number}
            </button>
          ))}
        </div>
      )}

      {current?.warning && (
        <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          ⚠ {current.warning}
        </p>
      )}

      {current && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between text-xs text-slate-400">
            <span>
              Confiance moyenne : {current.mean_confidence.toFixed(0)}% · cellules en
              orange = faible confiance (&lt;70%)
            </span>
          </div>
          <EditableTable data={current.data} onChange={handleCellChange} />
        </div>
      )}
    </div>
  );
}
