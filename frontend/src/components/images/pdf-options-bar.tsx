import type { ImageQuality, PageSize } from "../../api/types";

const QUALITY_OPTIONS: { value: ImageQuality; label: string }[] = [
  { value: "high", label: "Élevée" },
  { value: "standard", label: "Standard" },
  { value: "compact", label: "Compacte" },
];

const PAGE_SIZE_OPTIONS: { value: PageSize; label: string }[] = [
  { value: "a4", label: "A4 ajusté" },
  { value: "original", label: "Taille d'origine" },
];

interface PdfOptionsBarProps {
  name: string;
  onNameChange: (value: string) => void;
  quality: ImageQuality;
  onQualityChange: (value: ImageQuality) => void;
  pageSize: PageSize;
  onPageSizeChange: (value: PageSize) => void;
  createDocument: boolean;
  onCreateDocumentChange: (value: boolean) => void;
  onSortByName: () => void;
  onSortByDate: () => void;
  onGenerate: () => void;
  onSave: () => void;
  disabled: boolean;
  isGenerating: boolean;
  isSaving: boolean;
  progress: number;
}

export function PdfOptionsBar({
  name,
  onNameChange,
  quality,
  onQualityChange,
  pageSize,
  onPageSizeChange,
  createDocument,
  onCreateDocumentChange,
  onSortByName,
  onSortByDate,
  onGenerate,
  onSave,
  disabled,
  isGenerating,
  isSaving,
  progress,
}: PdfOptionsBarProps) {
  const busy = isGenerating || isSaving;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col text-sm font-medium text-slate-600">
          Nom du document
          <input
            type="text"
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            className="mt-1 w-48 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800"
          />
        </label>

        <label className="flex flex-col text-sm font-medium text-slate-600">
          Qualité
          <select
            value={quality}
            onChange={(e) => onQualityChange(e.target.value as ImageQuality)}
            className="mt-1 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800"
          >
            {QUALITY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col text-sm font-medium text-slate-600">
          Format de page
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(e.target.value as PageSize)}
            className="mt-1 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800"
          >
            {PAGE_SIZE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-2 pb-2 text-sm font-medium text-slate-600">
          <input
            type="checkbox"
            checked={createDocument}
            onChange={(e) => onCreateDocumentChange(e.target.checked)}
            className="h-4 w-4 rounded border-slate-300"
          />
          Lancer aussi l'extraction Excel (OCR)
        </label>

        <div className="ml-auto flex gap-2 pb-1">
          <button
            type="button"
            onClick={onSortByName}
            className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100"
          >
            Trier par nom
          </button>
          <button
            type="button"
            onClick={onSortByDate}
            className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100"
          >
            Trier par date
          </button>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onSave}
          disabled={disabled || busy}
          className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-40 hover:bg-slate-100"
        >
          {isSaving ? "Enregistrement…" : "Enregistrer le lot"}
        </button>
        <button
          type="button"
          onClick={onGenerate}
          disabled={disabled || busy}
          className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 hover:bg-brand-600"
        >
          {isGenerating ? "Génération…" : "Générer le PDF"}
        </button>

        {busy && (
          <div className="flex min-w-[160px] flex-1 items-center gap-2">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full bg-brand-500 transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
            <span className="text-xs text-slate-500">{progress}%</span>
          </div>
        )}
      </div>
    </div>
  );
}
