import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useState } from "react";

import type { PageItem } from "../../hooks/useImageBatch";
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
        className={`group relative flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm ${
          isDragging ? "opacity-50" : ""
        }`}
      >
        <div
          className="relative flex aspect-[3/4] min-h-[320px] cursor-grab items-center justify-center overflow-hidden bg-slate-100 active:cursor-grabbing"
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

          <span className="absolute left-2 top-2 flex h-8 min-w-8 items-center justify-center rounded-full bg-brand-600 px-2 text-sm font-bold text-white shadow">
            {position}
          </span>
        </div>

        <div className="flex items-center gap-2 border-t border-slate-100 p-2">
          <label className="flex items-center gap-1 text-xs text-slate-500">
            Ordre
            <select
              value={position}
              onChange={(e) => onSetPosition(item.clientId, Number(e.target.value))}
              className="rounded-md border border-slate-300 px-1.5 py-1 text-center text-xs text-slate-800"
            >
              {Array.from({ length: total }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>

          <div className="ml-auto flex gap-1">
            <button
              type="button"
              onClick={() => onRotate(item.clientId)}
              title="Pivoter de 90°"
              className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-700"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99"
                />
              </svg>
            </button>
            <button
              type="button"
              onClick={() => onRemove(item.clientId)}
              title="Retirer cette page"
              className="rounded-md p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-600"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        </div>

        <p className="truncate border-t border-slate-100 px-2 py-1 text-[11px] text-slate-400">
          {item.file.name}
        </p>
      </div>

      {showLightbox && (
        <PageLightbox
          src={item.previewUrl}
          rotation={item.rotation}
          alt={item.file.name}
          onClose={() => setShowLightbox(false)}
        />
      )}
    </>
  );
}
