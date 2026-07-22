export type DocumentStatus = "queued" | "processing" | "done" | "error";

export interface Cell {
  value: string;
  confidence: number;
}

export interface DocumentSummary {
  id: number;
  filename: string;
  status: DocumentStatus;
  page_count: number;
  language: string;
  preprocessing: boolean;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface PageData {
  page_number: number;
  text: string;
  data: Cell[][];
  mean_confidence: number;
  warning: string | null;
}

export interface DocumentDetail extends DocumentSummary {
  pages: PageData[];
}

export interface DocumentList {
  items: DocumentSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface PreviewResponse {
  document_id: number;
  filename: string;
  status: DocumentStatus;
  pages: PageData[];
}

export interface HealthResponse {
  status: string;
  tesseract_available: boolean;
  tesseract_languages: string[];
}

export interface UploadOptions {
  language: string;
  preprocessing: boolean;
}
