import type {
  ApiKey,
  ApiKeyCreateRequest,
  ApiKeyCreated,
  Cell,
  DocumentDetail,
  DocumentList,
  HealthResponse,
  PreviewResponse,
  UploadOptions,
} from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8082";
const STORAGE_KEY = "scantosheet.apiKey";
// Baked into the bundle at build time (see .env's VITE_API_KEY). Lets the app
// authenticate as a single shared identity without a login screen. A key
// saved via the admin page's ApiKeyField (localStorage) always overrides it.
const BUILT_IN_API_KEY = import.meta.env.VITE_API_KEY ?? "";

/** Error carrying the HTTP status and server-provided detail message. */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

/** The API key is kept in localStorage so it survives reloads. */
export function getApiKey(): string {
  return localStorage.getItem(STORAGE_KEY) ?? "";
}

export function setApiKey(key: string): void {
  const trimmed = key.trim();
  if (trimmed) {
    localStorage.setItem(STORAGE_KEY, trimmed);
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

export function clearApiKey(): void {
  localStorage.removeItem(STORAGE_KEY);
}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const key = getApiKey() || BUILT_IN_API_KEY;
  return key ? { ...extra, "X-API-Key": key } : extra;
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

/** Fetch a file with auth headers and hand it to the browser as a download. */
async function downloadBlob(url: string, fallbackName: string): Promise<void> {
  const response = await fetch(url, { headers: authHeaders() });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      /* keep status text */
    }
    throw new ApiError(response.status, detail);
  }

  // Prefer the server-provided filename from Content-Disposition.
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  const filename = match ? decodeURIComponent(match[1]) : fallbackName;

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
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
    return handle(
      await fetch(`${API_URL}/api/documents?${params}`, { headers: authHeaders() }),
    );
  },

  async getDocument(id: number): Promise<DocumentDetail> {
    return handle(
      await fetch(`${API_URL}/api/documents/${id}`, { headers: authHeaders() }),
    );
  },

  async getPreview(id: number): Promise<PreviewResponse> {
    return handle(
      await fetch(`${API_URL}/api/documents/${id}/preview`, { headers: authHeaders() }),
    );
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
      form.append("merge_pages", String(options.mergePages));

      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_URL}/api/documents`);
      const key = getApiKey() || BUILT_IN_API_KEY;
      if (key) {
        xhr.setRequestHeader("X-API-Key", key);
      }

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

  async updateData(
    id: number,
    pages: { page_number: number; data: Cell[][] }[],
  ): Promise<PreviewResponse> {
    return handle(
      await fetch(`${API_URL}/api/documents/${id}/data`, {
        method: "PUT",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ pages }),
      }),
    );
  },

  async deleteDocument(id: number): Promise<void> {
    return handle(
      await fetch(`${API_URL}/api/documents/${id}`, {
        method: "DELETE",
        headers: authHeaders(),
      }),
    );
  },

  /** Download the extraction. Uses fetch (not a plain link) to send the key. */
  async download(
    id: number,
    fmt: "xlsx" | "csv",
    merge = false,
    delimiter = ",",
  ): Promise<void> {
    const params = new URLSearchParams({ fmt, merge: String(merge), delimiter });
    return downloadBlob(
      `${API_URL}/api/documents/${id}/download?${params}`,
      `document_${id}.${fmt}`,
    );
  },

  // ----- Admin: API key management -----------------------------------------

  async listApiKeys(): Promise<ApiKey[]> {
    return handle(
      await fetch(`${API_URL}/api/admin/keys`, { headers: authHeaders() }),
    );
  },

  async createApiKey(payload: ApiKeyCreateRequest): Promise<ApiKeyCreated> {
    return handle(
      await fetch(`${API_URL}/api/admin/keys`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      }),
    );
  },

  async revokeApiKey(id: number): Promise<ApiKey> {
    return handle(
      await fetch(`${API_URL}/api/admin/keys/${id}`, {
        method: "DELETE",
        headers: authHeaders(),
      }),
    );
  },
};
