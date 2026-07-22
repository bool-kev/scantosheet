import { useCallback, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";

import { ApiError } from "../api/client";
import type { UploadOptions } from "../api/types";
import { useUpload } from "../hooks/useDocuments";

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

      const options: UploadOptions = { language, preprocessing };
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
    [language, preprocessing, upload],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    maxSize: MAX_SIZE_MB * 1024 * 1024,
    maxFiles: 1,
    multiple: false,
  });

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex flex-wrap items-end gap-4">
        <label className="flex flex-col text-sm font-medium text-slate-600">
          Langue du document
          <select
            className="mt-1 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
          >
            {LANGUAGES.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 pb-2 text-sm font-medium text-slate-600">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-slate-300"
            checked={preprocessing}
            onChange={(e) => setPreprocessing(e.target.checked)}
          />
          Prétraitement d'image
        </label>
      </div>

      <div
        {...getRootProps()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 text-center transition ${
          isDragActive
            ? "border-brand-500 bg-brand-50"
            : "border-slate-300 hover:border-brand-500 hover:bg-slate-50"
        }`}
      >
        <input {...getInputProps()} />
        <svg
          className="mb-3 h-10 w-10 text-slate-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3"
          />
        </svg>
        <p className="text-sm font-medium text-slate-700">
          {isDragActive
            ? "Déposez le PDF ici…"
            : "Glissez-déposez un PDF, ou cliquez pour parcourir"}
        </p>
        <p className="mt-1 text-xs text-slate-400">PDF uniquement · max {MAX_SIZE_MB} Mo</p>
      </div>

      {upload.isPending && (
        <div className="mt-4">
          <div className="mb-1 flex justify-between text-xs text-slate-500">
            <span>Envoi en cours…</span>
            <span>{progress}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full bg-brand-500 transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {error && (
        <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}
    </div>
  );
}
