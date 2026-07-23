import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Trash2 } from "lucide-react";

import type { DocumentSummary } from "../api/types";
import { useDeleteDocument, useDocuments } from "../hooks/useDocuments";
import { StatusBadge } from "./status-badge";
import { ConfirmDialog } from "./confirm-dialog";
import { Button } from "@/components/ui/button";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

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

/** Builds a compact page-number list with ellipses, e.g. 1 … 4 5 6 … 12. */
function paginationRange(current: number, total: number): (number | "ellipsis")[] {
  const pages = new Set([1, total, current - 1, current, current + 1]);
  const sorted = [...pages].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b);

  const result: (number | "ellipsis")[] = [];
  let previous = 0;
  for (const page of sorted) {
    if (previous && page - previous > 1) result.push("ellipsis");
    result.push(page);
    previous = page;
  }
  return result;
}

export function DocumentList() {
  const [page, setPage] = useState(1);
  const { data, isLoading, isFetching, isError, error } = useDocuments(page);
  const deleteDoc = useDeleteDocument();

  if (isLoading) {
    return (
      <div className="space-y-2 rounded-xl border">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-none first:rounded-t-xl last:rounded-b-xl" />
        ))}
      </div>
    );
  }
  if (isError) {
    return (
      <p className="py-8 text-center text-sm text-destructive">
        Impossible de charger les documents : {(error as Error).message}
      </p>
    );
  }

  const documents = data?.items ?? [];
  const total = data?.total ?? 0;
  const pageSize = data?.page_size ?? documents.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  if (documents.length === 0 && page === 1) {
    return (
      <p className="rounded-xl border border-dashed py-10 text-center text-sm text-muted-foreground">
        Aucun document pour le moment. Envoyez un PDF pour commencer.
      </p>
    );
  }

  const onDelete = (doc: DocumentSummary) => deleteDoc.mutate(doc.id);
  const goTo = (target: number) => setPage(Math.min(Math.max(target, 1), totalPages));

  return (
    <div className="space-y-3">
      <div className={cn("overflow-hidden rounded-xl border transition-opacity", isFetching && "opacity-60")}>
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Fichier</TableHead>
              <TableHead>Pages</TableHead>
              <TableHead>Statut</TableHead>
              <TableHead>Date</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {documents.map((doc) => (
              <TableRow key={doc.id}>
                <TableCell className="max-w-xs truncate font-medium">{doc.filename}</TableCell>
                <TableCell className="text-muted-foreground">{doc.page_count}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-1.5">
                    <StatusBadge status={doc.status} />
                    {doc.status === "error" && doc.error_message && (
                      <AlertTriangle
                        className="size-3.5 text-destructive"
                        aria-label={doc.error_message}
                      />
                    )}
                  </div>
                </TableCell>
                <TableCell className="text-muted-foreground">{formatDate(doc.created_at)}</TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    {doc.status === "done" && (
                      <Button asChild size="sm">
                        <Link to={`/documents/${doc.id}`}>Aperçu</Link>
                      </Button>
                    )}
                    <ConfirmDialog
                      trigger={
                        <Button variant="outline" size="icon-sm" aria-label="Supprimer">
                          <Trash2 />
                        </Button>
                      }
                      title="Supprimer ce document ?"
                      description={`« ${doc.filename} » et son résultat seront définitivement supprimés.`}
                      confirmLabel="Supprimer"
                      onConfirm={() => onDelete(doc)}
                    />
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {totalPages > 1 && (
        <Pagination>
          <PaginationContent>
            <PaginationItem>
              <PaginationPrevious
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  if (page > 1) goTo(page - 1);
                }}
                className={page === 1 ? "pointer-events-none opacity-40" : undefined}
              />
            </PaginationItem>

            {paginationRange(page, totalPages).map((entry, index) =>
              entry === "ellipsis" ? (
                <PaginationItem key={`ellipsis-${index}`}>
                  <span className="flex size-8 items-center justify-center text-muted-foreground">…</span>
                </PaginationItem>
              ) : (
                <PaginationItem key={entry}>
                  <PaginationLink
                    href="#"
                    isActive={entry === page}
                    onClick={(e) => {
                      e.preventDefault();
                      goTo(entry);
                    }}
                  >
                    {entry}
                  </PaginationLink>
                </PaginationItem>
              ),
            )}

            <PaginationItem>
              <PaginationNext
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  if (page < totalPages) goTo(page + 1);
                }}
                className={page === totalPages ? "pointer-events-none opacity-40" : undefined}
              />
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      )}
    </div>
  );
}
