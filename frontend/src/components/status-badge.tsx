import { CheckCircle2, CircleDashed, Loader2, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { DocumentStatus } from "../api/types";

const STYLES: Record<DocumentStatus, string> = {
  queued: "bg-muted text-muted-foreground",
  processing: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  done: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  error: "bg-destructive/15 text-destructive",
};

const ICONS: Record<DocumentStatus, typeof CheckCircle2> = {
  queued: CircleDashed,
  processing: Loader2,
  done: CheckCircle2,
  error: XCircle,
};

const LABELS: Record<DocumentStatus, string> = {
  queued: "En file",
  processing: "Traitement…",
  done: "Terminé",
  error: "Erreur",
};

export function StatusBadge({ status }: { status: DocumentStatus }) {
  const Icon = ICONS[status];
  return (
    <Badge className={cn(STYLES[status])}>
      <Icon className={cn("size-3", status === "processing" && "animate-spin")} aria-hidden="true" />
      {LABELS[status]}
    </Badge>
  );
}
