import apiClient from "./api";
import type {
  Document,
  PaginatedResponse,
  DocumentUploadResponse,
  DocumentChunk,
  DocumentTable,
  DocumentImage,
  DocumentVersion,
  DocumentStats,
  ExtractTextResponse,
  IngestionJobStatus,
} from "../types";

export interface DocumentListParams {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  file_type?: string;
  language?: string;
  sort_by?: string;
  sort_order?: "asc" | "desc";
}

// ── Document CRUD ───────────────────────────

export async function listDocuments(params?: DocumentListParams): Promise<PaginatedResponse<Document>> {
  const query: Record<string, string> = {};
  if (params?.page) query.page = String(params.page);
  if (params?.page_size) query.size = String(params.page_size);
  if (params?.search) query.search = params.search;
  if (params?.status) query.status = params.status;
  if (params?.file_type) query.file_type = params.file_type;
  if (params?.language) query.language = params.language;
  if (params?.sort_by) query.sort_by = params.sort_by;
  if (params?.sort_order) query.sort_order = params.sort_order;

  const { data } = await apiClient.get<PaginatedResponse<Document>>("/documents/", {
    params: query,
  });
  return data;
}

export async function getDocument(id: string): Promise<Document> {
  const { data } = await apiClient.get<Document>(`/documents/${id}`);
  return data;
}

export async function deleteDocument(id: string): Promise<{ message: string; code: string }> {
  const { data } = await apiClient.delete<{ message: string; code: string }>(`/documents/${id}`);
  return data;
}

export async function replaceDocument(id: string, file: File): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await apiClient.put<DocumentUploadResponse>(`/documents/${id}/replace`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120_000,
  });
  return data;
}

// ── Document Upload ─────────────────────────

export async function uploadDocument(
  file: File,
  onProgress?: (progress: number) => void,
): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const { data } = await apiClient.post<DocumentUploadResponse>("/documents/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 300_000,
    onUploadProgress: (progressEvent) => {
      if (progressEvent.total && onProgress) {
        onProgress(Math.round((progressEvent.loaded / progressEvent.total) * 100));
      }
    },
  });
  return data;
}

export async function uploadDocuments(
  files: File[],
  onProgress?: (fileIndex: number, progress: number) => void,
): Promise<DocumentUploadResponse[]> {
  const results: DocumentUploadResponse[] = [];
  for (let i = 0; i < files.length; i++) {
    const result = await uploadDocument(files[i], (progress) => {
      onProgress?.(i, progress);
    });
    results.push(result);
  }
  return results;
}

// ── Document Content ────────────────────────

export async function getDocumentText(id: string): Promise<ExtractTextResponse> {
  const { data } = await apiClient.get<ExtractTextResponse>(`/documents/${id}/text`);
  return data;
}

export async function getDocumentChunks(id: string): Promise<DocumentChunk[]> {
  const { data } = await apiClient.get<DocumentChunk[]>(`/documents/${id}/chunks`);
  return data;
}

export async function getDocumentTables(id: string): Promise<DocumentTable[]> {
  const { data } = await apiClient.get<DocumentTable[]>(`/documents/${id}/tables`);
  return data;
}

export async function getDocumentImages(id: string): Promise<DocumentImage[]> {
  const { data } = await apiClient.get<DocumentImage[]>(`/documents/${id}/images`);
  return data;
}

export async function getDocumentStats(id: string): Promise<DocumentStats> {
  const { data } = await apiClient.get<DocumentStats>(`/documents/${id}/stats`);
  return data;
}

export async function getDocumentVersions(id: string): Promise<DocumentVersion[]> {
  const { data } = await apiClient.get<DocumentVersion[]>(`/documents/${id}/versions`);
  return data;
}

// ── Processing & Ingestion ──────────────────

export async function getIngestionStatus(id: string): Promise<IngestionJobStatus> {
  const { data } = await apiClient.get<IngestionJobStatus>(`/documents/${id}/status`);
  return data;
}

export async function cancelIngestion(id: string): Promise<IngestionJobStatus> {
  const { data } = await apiClient.post<IngestionJobStatus>(`/documents/${id}/cancel`);
  return data;
}

export async function retryIngestion(id: string): Promise<IngestionJobStatus> {
  const { data } = await apiClient.post<IngestionJobStatus>(`/documents/${id}/retry`);
  return data;
}

export async function restoreVersion(id: string, version: number): Promise<void> {
  // Backend doesn't expose this endpoint directly; uses replace endpoint
  throw new Error("Version restore not directly supported. Use replace endpoint.");
}

export const documentService = {
  getDocument,
  listDocuments,
  deleteDocument,
  uploadDocument,
  uploadDocuments,
};
