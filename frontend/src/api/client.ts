import type {
  Cell,
  DocumentDetail,
  DocumentList,
  HealthResponse,
  PreviewResponse,
  UploadOptions,
} from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/** Error carrying the HTTP status and server-provided detail message. */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // response had no JSON body; keep the status text
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  baseUrl: API_URL,

  async health(): Promise<HealthResponse> {
    return handle(await fetch(`${API_URL}/api/health`));
  },

  async listDocuments(page = 1, pageSize = 20): Promise<DocumentList> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    return handle(await fetch(`${API_URL}/api/documents?${params}`));
  },

  async getDocument(id: number): Promise<DocumentDetail> {
    return handle(await fetch(`${API_URL}/api/documents/${id}`));
  },

  async getPreview(id: number): Promise<PreviewResponse> {
    return handle(await fetch(`${API_URL}/api/documents/${id}/preview`));
  },

  async uploadDocument(
    file: File,
    options: UploadOptions,
    onProgress?: (percent: number) => void,
  ): Promise<DocumentDetail> {
    // XMLHttpRequest is used (instead of fetch) to report upload progress.
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append("file", file);
      form.append("language", options.language);
      form.append("preprocessing", String(options.preprocessing));

      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_URL}/api/documents`);

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && onProgress) {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText));
        } else {
          let detail = xhr.statusText;
          try {
            detail = JSON.parse(xhr.responseText).detail ?? detail;
          } catch {
            /* keep status text */
          }
          reject(new ApiError(xhr.status, detail));
        }
      };
      xhr.onerror = () => reject(new ApiError(0, "Network error"));
      xhr.send(form);
    });
  },

  async updateData(id: number, pages: { page_number: number; data: Cell[][] }[]): Promise<PreviewResponse> {
    return handle(
      await fetch(`${API_URL}/api/documents/${id}/data`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pages }),
      }),
    );
  },

  async deleteDocument(id: number): Promise<void> {
    return handle(
      await fetch(`${API_URL}/api/documents/${id}`, { method: "DELETE" }),
    );
  },

  downloadUrl(id: number, fmt: "xlsx" | "csv", merge = false, delimiter = ","): string {
    const params = new URLSearchParams({ fmt, merge: String(merge), delimiter });
    return `${API_URL}/api/documents/${id}/download?${params}`;
  },
};
