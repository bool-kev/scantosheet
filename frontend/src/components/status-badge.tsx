import type { DocumentStatus } from "../api/types";

const STYLES: Record<DocumentStatus, string> = {
  queued: "bg-slate-100 text-slate-600",
  processing: "bg-amber-100 text-amber-700",
  done: "bg-emerald-100 text-emerald-700",
  error: "bg-red-100 text-red-700",
};

const LABELS: Record<DocumentStatus, string> = {
  queued: "En file",
  processing: "Traitement…",
  done: "Terminé",
  error: "Erreur",
};

export function StatusBadge({ status }: { status: DocumentStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${STYLES[status]}`}
    >
      {status === "processing" && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" />
      )}
      {LABELS[status]}
    </span>
  );
}
