import { Link } from "react-router-dom";
import { AlertTriangle, Trash2 } from "lucide-react";

import type { DocumentSummary } from "../api/types";
import { useDeleteDocument, useDocuments } from "../hooks/useDocuments";
import { StatusBadge } from "./status-badge";
import { ConfirmDialog } from "./confirm-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

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
  if (documents.length === 0) {
    return (
      <p className="rounded-xl border border-dashed py-10 text-center text-sm text-muted-foreground">
        Aucun document pour le moment. Envoyez un PDF pour commencer.
      </p>
    );
  }

  const onDelete = (doc: DocumentSummary) => deleteDoc.mutate(doc.id);

  return (
    <div className="overflow-hidden rounded-xl border">
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
  );
}
