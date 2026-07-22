import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { ApiKeyCreateRequest } from "../api/types";

/** Service health — also tells the UI whether authentication is enforced. */
export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    staleTime: 60_000,
  });
}

export function useApiKeys(enabled = true) {
  return useQuery({
    queryKey: ["api-keys"],
    queryFn: () => api.listApiKeys(),
    enabled,
    retry: false,
  });
}

export function useCreateApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ApiKeyCreateRequest) => api.createApiKey(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });
}

export function useRevokeApiKey() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.revokeApiKey(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });
}
