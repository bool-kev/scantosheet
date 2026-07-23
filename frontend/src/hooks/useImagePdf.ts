import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { BatchUpdateRequest, BuildPdfOptions } from "../api/types";

/** List saved image batches. */
export function useBatches() {
  return useQuery({
    queryKey: ["batches"],
    queryFn: () => api.listBatches(),
  });
}

/** Fetch one saved batch's metadata and images. */
export function useBatch(id: number | null) {
  return useQuery({
    queryKey: ["batch", id],
    queryFn: () => api.getBatch(id as number),
    enabled: id != null,
  });
}

export function useBuildPdf() {
  return useMutation({
    mutationFn: ({
      files,
      rotations,
      options,
      onProgress,
    }: {
      files: File[];
      rotations: number[];
      options: BuildPdfOptions;
      onProgress?: (percent: number) => void;
    }) => api.buildPdf(files, rotations, options, onProgress),
  });
}

export function useSaveBatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      files,
      rotations,
      options,
      onProgress,
    }: {
      files: File[];
      rotations: number[];
      options: { name: string; quality: string; pageSize: string };
      onProgress?: (percent: number) => void;
    }) => api.saveBatch(files, rotations, options, onProgress),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["batches"] });
    },
  });
}

export function useUpdateBatch(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: BatchUpdateRequest) => api.updateBatch(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["batch", id] });
      queryClient.invalidateQueries({ queryKey: ["batches"] });
    },
  });
}

export function useDeleteBatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteBatch(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["batches"] });
    },
  });
}
