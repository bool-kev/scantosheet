import { useCallback, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { UploadCloud } from "lucide-react";

import { ApiError } from "../api/client";
import type { UploadOptions } from "../api/types";
import { useUpload } from "../hooks/useDocuments";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

const LANGUAGES = [
  { value: "fra", label: "Français" },
  { value: "eng", label: "Anglais" },
  { value: "ara", label: "Arabe" },
  { value: "fra+eng", label: "Français + Anglais" },
];

const MAX_SIZE_MB = 50;

export function UploadDropzone() {
  const upload = useUpload();
  const [language, setLanguage] = useState("fra");
  const [preprocessing, setPreprocessing] = useState(true);
  const [mergePages, setMergePages] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const onDrop = useCallback(
    (accepted: File[], rejected: FileRejection[]) => {
      setError(null);
      if (rejected.length > 0) {
        setError(rejected[0].errors[0]?.message ?? "Fichier refusé");
        return;
      }
      const file = accepted[0];
      if (!file) return;

      const options: UploadOptions = { language, preprocessing, mergePages };
      setProgress(0);
      upload.mutate(
        { file, options, onProgress: setProgress },
        {
          onError: (err) => {
            setError(err instanceof ApiError ? err.message : "Échec de l'envoi");
          },
        },
      );
    },
    [language, preprocessing, mergePages, upload],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    maxSize: MAX_SIZE_MB * 1024 * 1024,
    maxFiles: 1,
    multiple: false,
  });

  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end gap-6">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="upload-language">Langue du document</Label>
            <Select value={language} onValueChange={setLanguage}>
              <SelectTrigger id="upload-language" className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LANGUAGES.map((l) => (
                  <SelectItem key={l.value} value={l.value}>
                    {l.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <label className="flex items-center gap-2 pb-2 text-sm font-medium">
            <Switch checked={preprocessing} onCheckedChange={setPreprocessing} />
            Prétraitement d'image
          </label>

          <label
            className="flex items-center gap-2 pb-2 text-sm font-medium"
            title="Toutes les pages dans une seule feuille Excel, au lieu d'une feuille par page"
          >
            <Switch checked={mergePages} onCheckedChange={setMergePages} />
            Fusionner les pages
          </label>
        </div>

        <div
          {...getRootProps()}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-12 text-center transition-colors",
            isDragActive
              ? "border-primary bg-accent"
              : "border-border hover:border-primary/50 hover:bg-muted/50",
          )}
        >
          <input {...getInputProps()} />
          <UploadCloud className="mb-3 size-9 text-muted-foreground" aria-hidden="true" />
          <p className="text-sm font-medium">
            {isDragActive
              ? "Déposez le PDF ici…"
              : "Glissez-déposez un PDF, ou cliquez pour parcourir"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            PDF uniquement · max {MAX_SIZE_MB} Mo
          </p>
        </div>

        {upload.isPending && (
          <div>
            <div className="mb-1 flex justify-between text-xs text-muted-foreground">
              <span>Envoi en cours…</span>
              <span>{progress}%</span>
            </div>
            <Progress value={progress} />
          </div>
        )}

        {error && (
          <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
