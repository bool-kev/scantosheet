import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useState } from "react";
import { RotateCw, X } from "lucide-react";

import type { PageItem } from "../../hooks/useImageBatch";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { PageLightbox } from "./page-lightbox";

interface PageCardProps {
  item: PageItem;
  position: number;
  total: number;
  onRotate: (clientId: string) => void;
  onRemove: (clientId: string) => void;
  onSetPosition: (clientId: string, position: number) => void;
}

export function PageCard({ item, position, total, onRotate, onRemove, onSetPosition }: PageCardProps) {
  const [showLightbox, setShowLightbox] = useState(false);

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: item.clientId,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <>
      <div
        ref={setNodeRef}
        style={style}
        className={cn(
          "group relative flex flex-col overflow-hidden rounded-xl border bg-card shadow-sm",
          isDragging && "opacity-50",
        )}
      >
        <div
          className="relative flex aspect-[3/4] min-h-[320px] cursor-grab items-center justify-center overflow-hidden bg-muted active:cursor-grabbing"
          {...attributes}
          {...listeners}
        >
          <img
            src={item.previewUrl}
            alt={item.file.name}
            onClick={(e) => {
              e.stopPropagation();
              setShowLightbox(true);
            }}
            className="max-h-full max-w-full cursor-zoom-in object-contain transition-transform"
            style={{ transform: `rotate(${item.rotation}deg)` }}
            draggable={false}
          />

          <span className="absolute left-2 top-2 flex h-8 min-w-8 items-center justify-center rounded-full bg-primary px-2 text-sm font-bold text-primary-foreground shadow">
            {position}
          </span>
        </div>

        <div className="flex items-center gap-2 border-t p-2">
          <Select
            value={String(position)}
            onValueChange={(v) => onSetPosition(item.clientId, Number(v))}
          >
            <SelectTrigger size="sm" aria-label="Ordre de la page" className="w-16">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Array.from({ length: total }, (_, i) => i + 1).map((n) => (
                <SelectItem key={n} value={String(n)}>
                  {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <div className="ml-auto flex gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={() => onRotate(item.clientId)}
              aria-label="Pivoter de 90°"
            >
              <RotateCw />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={() => onRemove(item.clientId)}
              aria-label="Retirer cette page"
              className="hover:bg-destructive/10 hover:text-destructive"
            >
              <X />
            </Button>
          </div>
        </div>

        <p className="truncate border-t px-2 py-1 text-[11px] text-muted-foreground">
          {item.file.name}
        </p>
      </div>

      <PageLightbox
        src={item.previewUrl}
        rotation={item.rotation}
        alt={item.file.name}
        open={showLightbox}
        onOpenChange={setShowLightbox}
      />
    </>
  );
}
