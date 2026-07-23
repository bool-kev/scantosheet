import { useCallback, useEffect, useReducer, useRef } from "react";

import { api } from "../api/client";
import type { ImageBatchDetail, ImageQuality, PageRotation, PageSize } from "../api/types";

/** One page in the local (in-memory) working set, before it is saved or built. */
export interface PageItem {
  clientId: string;
  file: File;
  previewUrl: string;
  rotation: PageRotation;
  /** Present once this page has been persisted as part of a saved batch. */
  serverImageId?: number;
}

export interface ImageBatchState {
  batchId: number | null;
  name: string;
  quality: ImageQuality;
  pageSize: PageSize;
  items: PageItem[];
  /** True whenever local state has changed since the last successful save. */
  isDirty: boolean;
}

const initialState: ImageBatchState = {
  batchId: null,
  name: "Sans titre",
  quality: "standard",
  pageSize: "a4",
  items: [],
  isDirty: false,
};

type Action =
  | { type: "add"; items: PageItem[] }
  | { type: "remove"; clientId: string }
  | { type: "move"; from: number; to: number }
  | { type: "setPosition"; clientId: string; position: number }
  | { type: "rotate"; clientId: string }
  | { type: "sortByName" }
  | { type: "sortByDate" }
  | { type: "setName"; name: string }
  | { type: "setQuality"; quality: ImageQuality }
  | { type: "setPageSize"; pageSize: PageSize }
  | { type: "markSaved"; batchId: number }
  | { type: "hydrate"; state: Omit<ImageBatchState, "isDirty"> }
  | { type: "reset" };

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function reducer(state: ImageBatchState, action: Action): ImageBatchState {
  switch (action.type) {
    case "add":
      return { ...state, items: [...state.items, ...action.items], isDirty: true };

    case "remove":
      return {
        ...state,
        items: state.items.filter((item) => item.clientId !== action.clientId),
        isDirty: true,
      };

    case "move": {
      const items = [...state.items];
      const [moved] = items.splice(action.from, 1);
      items.splice(action.to, 0, moved);
      return { ...state, items, isDirty: true };
    }

    case "setPosition": {
      const fromIndex = state.items.findIndex((item) => item.clientId === action.clientId);
      if (fromIndex === -1) return state;
      const toIndex = clamp(action.position - 1, 0, state.items.length - 1);
      if (fromIndex === toIndex) return state;
      // Swap with whichever page currently holds that slot, instead of
      // shifting every page in between: picking "2" when a page is already
      // at position 2 hands that page the position we just vacated.
      const items = [...state.items];
      [items[fromIndex], items[toIndex]] = [items[toIndex], items[fromIndex]];
      return { ...state, items, isDirty: true };
    }

    case "rotate":
      return {
        ...state,
        items: state.items.map((item) =>
          item.clientId === action.clientId
            ? { ...item, rotation: (((item.rotation + 90) % 360) as PageRotation) }
            : item,
        ),
        isDirty: true,
      };

    case "sortByName": {
      const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
      const items = [...state.items].sort((a, b) => collator.compare(a.file.name, b.file.name));
      return { ...state, items, isDirty: true };
    }

    case "sortByDate": {
      const items = [...state.items].sort((a, b) => a.file.lastModified - b.file.lastModified);
      return { ...state, items, isDirty: true };
    }

    case "setName":
      return { ...state, name: action.name, isDirty: true };

    case "setQuality":
      return { ...state, quality: action.quality, isDirty: true };

    case "setPageSize":
      return { ...state, pageSize: action.pageSize, isDirty: true };

    case "markSaved":
      return { ...state, batchId: action.batchId, isDirty: false };

    case "hydrate":
      return { ...action.state, isDirty: false };

    case "reset":
      return initialState;

    default:
      return state;
  }
}

/** Manages the in-memory working set of pages for the Images -> PDF module. */
export function useImageBatch() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const itemsRef = useRef(state.items);
  itemsRef.current = state.items;

  const addFiles = useCallback((files: File[]) => {
    const existing = new Set(itemsRef.current.map((item) => `${item.file.name}:${item.file.size}`));
    const items: PageItem[] = files
      .filter((file) => !existing.has(`${file.name}:${file.size}`))
      .map((file) => ({
        clientId: crypto.randomUUID(),
        file,
        previewUrl: URL.createObjectURL(file),
        rotation: 0,
      }));
    if (items.length > 0) {
      dispatch({ type: "add", items });
    }
  }, []);

  const remove = useCallback((clientId: string) => {
    const item = itemsRef.current.find((candidate) => candidate.clientId === clientId);
    if (item) URL.revokeObjectURL(item.previewUrl);
    dispatch({ type: "remove", clientId });
  }, []);

  const move = useCallback((from: number, to: number) => {
    dispatch({ type: "move", from, to });
  }, []);

  const setPosition = useCallback((clientId: string, position: number) => {
    dispatch({ type: "setPosition", clientId, position });
  }, []);

  const rotate = useCallback((clientId: string) => {
    dispatch({ type: "rotate", clientId });
  }, []);

  const sortByName = useCallback(() => dispatch({ type: "sortByName" }), []);
  const sortByDate = useCallback(() => dispatch({ type: "sortByDate" }), []);
  const setName = useCallback((name: string) => dispatch({ type: "setName", name }), []);
  const setQuality = useCallback(
    (quality: ImageQuality) => dispatch({ type: "setQuality", quality }),
    [],
  );
  const setPageSize = useCallback(
    (pageSize: PageSize) => dispatch({ type: "setPageSize", pageSize }),
    [],
  );
  const markSaved = useCallback((batchId: number) => dispatch({ type: "markSaved", batchId }), []);

  const reset = useCallback(() => {
    itemsRef.current.forEach((item) => URL.revokeObjectURL(item.previewUrl));
    dispatch({ type: "reset" });
  }, []);

  /** Load a saved batch: fetches each image's bytes so previews work offline of the server URL. */
  const hydrate = useCallback(async (batch: ImageBatchDetail) => {
    itemsRef.current.forEach((item) => URL.revokeObjectURL(item.previewUrl));

    const sorted = [...batch.images].sort((a, b) => a.position - b.position);
    const items: PageItem[] = await Promise.all(
      sorted.map(async (image) => {
        const blob = await api.fetchBatchImageBlob(batch.id, image.id);
        const file = new File([blob], image.filename, { type: blob.type });
        return {
          clientId: crypto.randomUUID(),
          file,
          previewUrl: URL.createObjectURL(file),
          rotation: image.rotation,
          serverImageId: image.id,
        };
      }),
    );

    dispatch({
      type: "hydrate",
      state: {
        batchId: batch.id,
        name: batch.name,
        quality: batch.quality,
        pageSize: batch.page_size,
        items,
      },
    });
  }, []);

  useEffect(() => {
    return () => {
      itemsRef.current.forEach((item) => URL.revokeObjectURL(item.previewUrl));
    };
  }, []);

  return {
    ...state,
    addFiles,
    remove,
    move,
    setPosition,
    rotate,
    sortByName,
    sortByDate,
    setName,
    setQuality,
    setPageSize,
    markSaved,
    reset,
    hydrate,
  };
}

/** Warns the user before they navigate away with unsaved local changes. */
export function useWarnBeforeUnload(when: boolean): void {
  useEffect(() => {
    if (!when) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [when]);
}
