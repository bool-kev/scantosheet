import { ArrowDownAZ, Calendar, Download, Save } from "lucide-react";

import type { ImageQuality, PageSize } from "../../api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
    <Card>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="batch-name">Nom du document</Label>
            <Input
              id="batch-name"
              value={name}
              onChange={(e) => onNameChange(e.target.value)}
              className="w-48"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="batch-quality">Qualité</Label>
            <Select value={quality} onValueChange={(v) => onQualityChange(v as ImageQuality)}>
              <SelectTrigger id="batch-quality" className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {QUALITY_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="batch-page-size">Format de page</Label>
            <Select value={pageSize} onValueChange={(v) => onPageSizeChange(v as PageSize)}>
              <SelectTrigger id="batch-page-size" className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <label className="flex items-center gap-2 pb-2 text-sm font-medium">
            <Switch checked={createDocument} onCheckedChange={onCreateDocumentChange} />
            Lancer aussi l'extraction Excel (OCR)
          </label>

          <div className="ml-auto flex gap-2 pb-1">
            <Button type="button" variant="outline" size="sm" onClick={onSortByName}>
              <ArrowDownAZ /> Trier par nom
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={onSortByDate}>
              <Calendar /> Trier par date
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" variant="outline" onClick={onSave} disabled={disabled || busy}>
            <Save />
            {isSaving ? "Enregistrement…" : "Enregistrer le lot"}
          </Button>
          <Button type="button" onClick={onGenerate} disabled={disabled || busy}>
            <Download />
            {isGenerating ? "Génération…" : "Générer le PDF"}
          </Button>

          {busy && (
            <div className="flex min-w-[160px] flex-1 items-center gap-2">
              <Progress value={progress} className="flex-1" />
              <span className="text-xs text-muted-foreground">{progress}%</span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
