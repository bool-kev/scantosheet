import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  rectSortingStrategy,
  sortableKeyboardCoordinates,
} from "@dnd-kit/sortable";
import { useState } from "react";

import type { PageItem } from "../../hooks/useImageBatch";
import { PageCard } from "./page-card";

interface PageGridProps {
  items: PageItem[];
  onMove: (from: number, to: number) => void;
  onRotate: (clientId: string) => void;
  onRemove: (clientId: string) => void;
  onSetPosition: (clientId: string, position: number) => void;
}

export function PageGrid({ items, onMove, onRotate, onRemove, onSetPosition }: PageGridProps) {
  const [activeId, setActiveId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(String(event.active.id));
  };

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveId(null);
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const from = items.findIndex((item) => item.clientId === active.id);
    const to = items.findIndex((item) => item.clientId === over.id);
    if (from !== -1 && to !== -1) {
      onMove(from, to);
    }
  };

  const activeItem = activeId ? items.find((item) => item.clientId === activeId) : null;

  if (items.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-slate-200 py-12 text-center text-sm text-slate-400">
        Aucune page pour le moment. Déposez des images ci-dessus.
      </p>
    );
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <SortableContext items={items.map((item) => item.clientId)} strategy={rectSortingStrategy}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item, index) => (
            <PageCard
              key={item.clientId}
              item={item}
              position={index + 1}
              total={items.length}
              onRotate={onRotate}
              onRemove={onRemove}
              onSetPosition={onSetPosition}
            />
          ))}
        </div>
      </SortableContext>

      <DragOverlay>
        {activeItem && (
          <div className="rounded-xl border border-brand-500 bg-white shadow-lg">
            <img
              src={activeItem.previewUrl}
              alt=""
              className="aspect-[3/4] max-h-80 w-full object-contain"
              style={{ transform: `rotate(${activeItem.rotation}deg)` }}
            />
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}
