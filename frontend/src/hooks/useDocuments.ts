import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Cell, UploadOptions } from "../api/types";

/** List documents. Polls while any document is still being processed. */
export function useDocuments() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: () => api.listDocuments(1, 100),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      const active = items.some(
        (d) => d.status === "queued" || d.status === "processing",
      );
      return active ? 2000 : false;
    },
  });
}

/** Fetch a single document detail, polling while it is still processing. */
export function useDocument(id: number | null) {
  return useQuery({
    queryKey: ["document", id],
    queryFn: () => api.getDocument(id as number),
    enabled: id != null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "processing" ? 2000 : false;
    },
  });
}

export function useUpload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      file,
      options,
      onProgress,
    }: {
      file: File;
      options: UploadOptions;
      onProgress?: (percent: number) => void;
    }) => api.uploadDocument(file, options, onProgress),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteDocument(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useUpdateData(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (pages: { page_number: number; data: Cell[][] }[]) =>
      api.updateData(id, pages),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["document", id] });
    },
  });
}
