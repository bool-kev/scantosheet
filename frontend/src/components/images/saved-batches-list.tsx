import { Trash2 } from "lucide-react";

import type { ImageBatchSummary } from "../../api/types";
import { useBatches, useDeleteBatch } from "../../hooks/useImagePdf";
import { ConfirmDialog } from "../confirm-dialog";
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
    return (
      <div className="space-y-2 rounded-xl border">
        {Array.from({ length: 2 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-none first:rounded-t-xl last:rounded-b-xl" />
        ))}
      </div>
    );
  }
  if (isError) {
    return (
      <p className="py-6 text-center text-sm text-destructive">
        Impossible de charger les lots enregistrés.
      </p>
    );
  }

  const batches = data ?? [];
  if (batches.length === 0) {
    return (
      <p className="rounded-xl border border-dashed py-10 text-center text-sm text-muted-foreground">
        Aucun lot enregistré pour le moment.
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Nom</TableHead>
            <TableHead>Images</TableHead>
            <TableHead>Dernière modification</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {batches.map((batch) => (
            <TableRow key={batch.id}>
              <TableCell className="max-w-xs truncate font-medium">{batch.name}</TableCell>
              <TableCell className="text-muted-foreground">{batch.image_count}</TableCell>
              <TableCell className="text-muted-foreground">{formatDate(batch.updated_at)}</TableCell>
              <TableCell className="text-right">
                <div className="flex justify-end gap-2">
                  <Button size="sm" onClick={() => onOpen(batch)}>
                    Ouvrir
                  </Button>
                  <ConfirmDialog
                    trigger={
                      <Button variant="outline" size="icon-sm" aria-label="Supprimer">
                        <Trash2 />
                      </Button>
                    }
                    title="Supprimer ce lot ?"
                    description={`« ${batch.name} » et ses images seront définitivement supprimés.`}
                    confirmLabel="Supprimer"
                    onConfirm={() => deleteBatch.mutate(batch.id)}
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
