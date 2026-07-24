import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, Download, FileSpreadsheet, Undo2 } from "lucide-react";

import { ApiError, api } from "../api/client";
import type { Cell, PageData } from "../api/types";
import { EditableTable } from "../components/editable-table";
import { StatusBadge } from "../components/status-badge";
import { useDocument, useUpdateData } from "../hooks/useDocuments";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function PreviewPage() {
  const { id } = useParams<{ id: string }>();
  const documentId = Number(id);
  const { data: doc, isLoading, isError, error } = useDocument(documentId);
  const updateData = useUpdateData(documentId);

  const [pages, setPages] = useState<PageData[]>([]);
  const [history, setHistory] = useState<PageData[][]>([]);
  const [activePage, setActivePage] = useState(0);
  const [merge, setMerge] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const MAX_HISTORY = 100;

  // Sync local editable copy whenever the fetched document changes.
  useEffect(() => {
    if (doc?.pages) {
      setPages(doc.pages);
      setHistory([]);
      setDirty(false);
    }
  }, [doc?.id, doc?.pages]);

  // Seed the export layout from the choice made at upload time.
  useEffect(() => {
    if (doc) {
      setMerge(doc.merge_pages);
    }
  }, [doc?.id, doc?.merge_pages]);

  // Ctrl/Cmd+S saves, Ctrl/Cmd+Z undoes. The listener is registered once
  // (hooks must run unconditionally, before the early returns below), but
  // reads through refs so it always calls the latest handleSave/handleUndo.
  const handleSaveRef = useRef<() => void>(() => {});
  const handleUndoRef = useRef<() => void>(() => {});

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      const key = event.key.toLowerCase();
      if (key === "s") {
        event.preventDefault();
        handleSaveRef.current();
      } else if (key === "z" && !event.shiftKey) {
        event.preventDefault();
        handleUndoRef.current();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  if (isLoading) {
    return <p className="p-10 text-center text-muted-foreground">Chargement…</p>;
  }
  if (isError || !doc) {
    return (
      <div className="p-10 text-center">
        <p className="text-destructive">{(error as Error)?.message ?? "Document introuvable"}</p>
        <Button asChild variant="link" className="mt-4">
          <Link to="/">Retour</Link>
        </Button>
      </div>
    );
  }

  /** Applies a mutation to `pages` and records the prior state for undo. */
  const commit = (mutate: (prev: PageData[]) => PageData[]) => {
    setHistory((h) => [...h.slice(-(MAX_HISTORY - 1)), pages]);
    setPages(mutate);
    setDirty(true);
    setSaved(false);
  };

  const handleCellChange = (rowIndex: number, colIndex: number, value: string) => {
    commit((prev) => {
      const next = prev.map((p) => ({ ...p, data: p.data.map((row) => [...row]) }));
      const page = next[activePage];
      while (page.data[rowIndex].length <= colIndex) {
        page.data[rowIndex].push({ value: "", confidence: 100 });
      }
      const existing = page.data[rowIndex][colIndex];
      page.data[rowIndex][colIndex] = { value, confidence: existing?.confidence ?? 100 };
      return next;
    });
  };

  const handleAddRow = (afterRow: number | null) => {
    commit((prev) => {
      const next = prev.map((p) => ({ ...p, data: p.data.map((row) => [...row]) }));
      const page = next[activePage];
      const columnCount = Math.max(1, ...page.data.map((row) => row.length));
      const newRow = Array.from({ length: columnCount }, () => ({ value: "", confidence: 100 }));
      const insertAt = afterRow !== null ? Math.min(afterRow + 1, page.data.length) : page.data.length;
      page.data.splice(insertAt, 0, newRow);
      return next;
    });
  };

  const handleAddColumn = (afterColumn: number | null) => {
    commit((prev) => {
      const next = prev.map((p) => ({ ...p, data: p.data.map((row) => [...row]) }));
      const page = next[activePage];
      page.data.forEach((row) => {
        const insertAt = afterColumn !== null ? Math.min(afterColumn + 1, row.length) : row.length;
        row.splice(insertAt, 0, { value: "", confidence: 100 });
      });
      return next;
    });
  };

  const handleDeleteRow = (rowIndex: number) => {
    commit((prev) => {
      const next = prev.map((p) => ({ ...p, data: p.data.map((row) => [...row]) }));
      next[activePage].data.splice(rowIndex, 1);
      return next;
    });
  };

  const handleDeleteColumn = (colIndex: number) => {
    commit((prev) => {
      const next = prev.map((p) => ({ ...p, data: p.data.map((row) => [...row]) }));
      next[activePage].data.forEach((row) => {
        if (colIndex < row.length) row.splice(colIndex, 1);
      });
      return next;
    });
  };

  const handleUndo = () => {
    if (history.length === 0) return;
    const previous = history[history.length - 1];
    setPages(previous);
    setHistory(history.slice(0, -1));
    setDirty(true);
    setSaved(false);
  };

  const handleSave = () => {
    if (!dirty || updateData.isPending) return;
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

  handleSaveRef.current = handleSave;
  handleUndoRef.current = handleUndo;

  // Downloads go through fetch (not a plain link) so the API key header travels
  // with the request.
  const handleDownload = async (fmt: "xlsx" | "csv") => {
    setDownloadError(null);
    try {
      await api.download(doc.id, fmt, fmt === "xlsx" ? merge : false);
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.message : "Échec du téléchargement");
    }
  };

  const current = pages[activePage];

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <Button asChild variant="link" className="h-auto p-0 text-sm">
            <Link to="/">
              <ArrowLeft className="size-3.5" /> Retour à l'historique
            </Link>
          </Button>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">{doc.filename}</h1>
          <div className="mt-1.5 flex items-center gap-3 text-sm text-muted-foreground">
            <StatusBadge status={doc.status} />
            <span>{doc.page_count} page(s)</span>
            <span>Langue : {doc.language}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm font-medium">
            <Switch checked={merge} onCheckedChange={setMerge} />
            Fusionner les pages
          </label>
          <Button
            variant="outline"
            onClick={handleUndo}
            disabled={history.length === 0}
            title="Annuler (Ctrl+Z)"
          >
            <Undo2 /> Annuler
          </Button>
          <Button
            variant="outline"
            onClick={handleSave}
            disabled={!dirty || updateData.isPending}
            title="Enregistrer (Ctrl+S)"
          >
            {updateData.isPending ? "Enregistrement…" : "Enregistrer"}
          </Button>
          <Button onClick={() => handleDownload("xlsx")}>
            <FileSpreadsheet /> Excel (.xlsx)
          </Button>
          <Button variant="outline" onClick={() => handleDownload("csv")}>
            <Download /> CSV
          </Button>
        </div>
      </div>

      {downloadError && (
        <p className="mb-4 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {downloadError}
        </p>
      )}
      {saved && (
        <p className="mb-4 rounded-lg bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-400">
          Modifications enregistrées.
        </p>
      )}
      {dirty && (
        <p className="mb-4 flex items-center gap-2 rounded-lg bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
          <AlertTriangle className="size-4 shrink-0" />
          Modifications non enregistrées — pensez à enregistrer avant de télécharger.
        </p>
      )}

      {pages.length > 1 && (
        <Tabs
          value={String(activePage)}
          onValueChange={(v) => setActivePage(Number(v))}
          className="mb-4"
        >
          <TabsList
            className="h-auto w-full justify-start overflow-x-auto bg-transparent p-0"
            variant="line"
          >
            {pages.map((p, index) => (
              <TabsTrigger key={p.page_number} value={String(index)} className="shrink-0">
                Page {p.page_number}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      )}

      {current?.warning && (
        <p className="mb-4 flex items-center gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <AlertTriangle className="size-4 shrink-0" />
          {current.warning}
        </p>
      )}

      {current && (
        <Card>
          <CardContent>
            <div className="mb-3 flex items-center justify-between text-xs text-muted-foreground">
              <span>
                Confiance moyenne : {current.mean_confidence.toFixed(0)}% · cellules en orange =
                faible confiance (&lt;70%)
              </span>
            </div>
            <EditableTable
              data={current.data}
              onChange={handleCellChange}
              onAddRow={handleAddRow}
              onAddColumn={handleAddColumn}
              onDeleteRow={handleDeleteRow}
              onDeleteColumn={handleDeleteColumn}
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
