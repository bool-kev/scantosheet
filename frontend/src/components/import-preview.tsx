import { useState } from "react";
import { AlertTriangle, Download } from "lucide-react";

import { ApiError, api } from "../api/client";
import { useNormalized } from "../hooks/useDocuments";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface ImportPreviewProps {
  documentId: number;
}

/**
 * Read-only view of the document mapped onto the import schema: the rows that
 * land in the Excel "Import" sheet. It reflects the last *saved* page data.
 */
export function ImportPreview({ documentId }: ImportPreviewProps) {
  const { data, isLoading, isError } = useNormalized(documentId);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  if (isLoading || isError || !data) return null;
  if (data.rows.length === 0 && data.warnings.length === 0) return null;

  const doubtfulCount = data.rows.reduce((total, row) => total + row.doubtful.length, 0);

  const handleDownload = async () => {
    setDownloadError(null);
    try {
      await api.download(documentId, "csv", false, ",", "import");
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.message : "Échec du téléchargement");
    }
  };

  return (
    <Card className="mt-6">
      <CardContent>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">Données prêtes à l'import</h2>
            <p className="text-xs text-muted-foreground">
              {data.rows.length} ligne(s) · {doubtfulCount} champ(s) à vérifier (en jaune) · reflète
              les dernières modifications enregistrées
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={handleDownload}>
            <Download /> CSV d'import
          </Button>
        </div>

        {downloadError && (
          <p className="mb-3 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {downloadError}
          </p>
        )}
        {data.warnings.map((warning) => (
          <p
            key={warning}
            className="mb-3 flex items-center gap-2 rounded-lg bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400"
          >
            <AlertTriangle className="size-4 shrink-0" />
            {warning}
          </p>
        ))}

        {data.rows.length > 0 && (
          <div className="max-h-[32rem] overflow-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Page</TableHead>
                  {data.columns.map((column) => (
                    <TableHead key={column}>{column}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.rows.map((row, index) => (
                  <TableRow key={index}>
                    <TableCell className="text-muted-foreground">{row.page}</TableCell>
                    {data.columns.map((column) => (
                      <TableCell
                        key={column}
                        className={
                          row.doubtful.includes(column)
                            ? "bg-amber-500/20 whitespace-normal"
                            : "whitespace-normal"
                        }
                      >
                        {row.values[column] ?? ""}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
