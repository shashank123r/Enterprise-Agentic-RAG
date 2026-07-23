import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listDocuments,
  getDocument,
  getDocumentChunks,
  getDocumentTables,
  getDocumentImages,
  getDocumentVersions,
  getDocumentText,
  getDocumentStats,
  getIngestionStatus,
  uploadDocument,
  uploadDocuments,
  deleteDocument,
  replaceDocument,
  cancelIngestion,
  retryIngestion,
  restoreVersion,
  type DocumentListParams,
  type DocumentUploadResponse,
} from "../services/document.service";
import { indexingService } from "../services/indexing.service";
import { useNotificationsStore } from "../store";

// ── Query Keys ──────────────────────────────

export const documentKeys = {
  all: ["documents"] as const,
  lists: () => [...documentKeys.all, "list"] as const,
  list: (params: DocumentListParams) => [...documentKeys.lists(), params] as const,
  details: () => [...documentKeys.all, "detail"] as const,
  detail: (id: string) => [...documentKeys.details(), id] as const,
  chunks: (id: string) => [...documentKeys.detail(id), "chunks"] as const,
  tables: (id: string) => [...documentKeys.detail(id), "tables"] as const,
  images: (id: string) => [...documentKeys.detail(id), "images"] as const,
  versions: (id: string) => [...documentKeys.detail(id), "versions"] as const,
  text: (id: string) => [...documentKeys.detail(id), "text"] as const,
  stats: (id: string) => [...documentKeys.detail(id), "stats"] as const,
  ingestionStatus: (id: string) => [...documentKeys.detail(id), "ingestion-status"] as const,
  indexingJobs: (id: string) => [...documentKeys.detail(id), "indexing-jobs"] as const,
};

// ── Hooks ───────────────────────────────────

export function useDocumentsList(params: DocumentListParams = {}) {
  return useQuery({
    queryKey: documentKeys.list(params),
    queryFn: () => listDocuments(params),
  });
}

export function useDocument(id: string) {
  return useQuery({
    queryKey: documentKeys.detail(id),
    queryFn: () => getDocument(id),
    enabled: !!id,
  });
}

export function useDocumentChunks(id: string) {
  return useQuery({
    queryKey: documentKeys.chunks(id),
    queryFn: () => getDocumentChunks(id),
    enabled: !!id,
  });
}

export function useDocumentTables(id: string) {
  return useQuery({
    queryKey: documentKeys.tables(id),
    queryFn: () => getDocumentTables(id),
    enabled: !!id,
  });
}

export function useDocumentImages(id: string) {
  return useQuery({
    queryKey: documentKeys.images(id),
    queryFn: () => getDocumentImages(id),
    enabled: !!id,
  });
}

export function useDocumentText(id: string) {
  return useQuery({
    queryKey: documentKeys.text(id),
    queryFn: () => getDocumentText(id),
    enabled: !!id,
  });
}

export function useDocumentVersions(id: string) {
  return useQuery({
    queryKey: documentKeys.versions(id),
    queryFn: () => getDocumentVersions(id),
    enabled: !!id,
  });
}

export function useDocumentStats(id: string) {
  return useQuery({
    queryKey: documentKeys.stats(id),
    queryFn: () => getDocumentStats(id),
    enabled: !!id,
  });
}

export function useIngestionStatus(id: string) {
  return useQuery({
    queryKey: documentKeys.ingestionStatus(id),
    queryFn: () => getIngestionStatus(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "completed" || status === "failed" || status === "cancelled") {
        return false;
      }
      return 3000;
    },
  });
}

export function useIndexingJobs(documentId: string) {
  return useQuery({
    queryKey: documentKeys.indexingJobs(documentId),
    queryFn: () => indexingService.listJobs(documentId),
    enabled: !!documentId,
  });
}

// ── Mutations ───────────────────────────────

export function useUploadDocument() {
  const queryClient = useQueryClient();
  const addNotification = useNotificationsStore((s) => s.addNotification);

  return useMutation({
    mutationFn: ({ file, onProgress }: { file: File; onProgress?: (p: number) => void }) =>
      uploadDocument(file, onProgress),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
      addNotification({
        type: "success",
        title: "Upload complete",
        message: `${data.document.original_filename} uploaded successfully`,
      });
    },
    onError: (error: Error) => {
      addNotification({
        type: "error",
        title: "Upload failed",
        message: error.message,
      });
    },
  });
}

export function useUploadDocuments() {
  const queryClient = useQueryClient();
  const addNotification = useNotificationsStore((s) => s.addNotification);

  return useMutation({
    mutationFn: ({
      files,
      onProgress,
    }: {
      files: File[];
      onProgress?: (fileIndex: number, progress: number) => void;
    }) => uploadDocuments(files, onProgress),
    onSuccess: (results) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
      addNotification({
        type: "success",
        title: "Uploads complete",
        message: `${results.length} document(s) uploaded successfully`,
      });
    },
    onError: (error: Error) => {
      addNotification({
        type: "error",
        title: "Batch upload failed",
        message: error.message,
      });
    },
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  const addNotification = useNotificationsStore((s) => s.addNotification);

  return useMutation({
    mutationFn: (id: string) => deleteDocument(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
      addNotification({
        type: "success",
        title: "Document deleted",
        message: "The document has been deleted",
      });
    },
    onError: (error: Error) => {
      addNotification({
        type: "error",
        title: "Delete failed",
        message: error.message,
      });
    },
  });
}

export function useReplaceDocument() {
  const queryClient = useQueryClient();
  const addNotification = useNotificationsStore((s) => s.addNotification);

  return useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => replaceDocument(id, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentKeys.all });
      addNotification({
        type: "success",
        title: "Document replaced",
        message: "The document has been replaced and will be re-processed",
      });
    },
    onError: (error: Error) => {
      addNotification({
        type: "error",
        title: "Replace failed",
        message: error.message,
      });
    },
  });
}

export function useCancelIngestion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => cancelIngestion(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.ingestionStatus(id) });
      queryClient.invalidateQueries({ queryKey: documentKeys.detail(id) });
    },
  });
}

export function useRetryIngestion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => retryIngestion(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.ingestionStatus(id) });
      queryClient.invalidateQueries({ queryKey: documentKeys.detail(id) });
    },
  });
}

export function useStartIndexing() {
  const queryClient = useQueryClient();
  const addNotification = useNotificationsStore((s) => s.addNotification);

  return useMutation({
    mutationFn: ({ documentId, collectionName = "documents" }: { documentId: string; collectionName?: string }) =>
      indexingService.startIndexing(documentId, collectionName),
    onSuccess: (_data) => {
      queryClient.invalidateQueries({ queryKey: ["indexing"] });
      addNotification({
        type: "success",
        title: "Indexing started",
        message: "Document indexing has been queued",
      });
    },
    onError: (error: Error) => {
      addNotification({
        type: "error",
        title: "Indexing failed",
        message: error.message,
      });
    },
  });
}

export function useCancelIndexing() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => indexingService.cancelJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["indexing"] });
    },
  });
}

export function useDeleteDocumentIndex() {
  const queryClient = useQueryClient();
  const addNotification = useNotificationsStore((s) => s.addNotification);

  return useMutation({
    mutationFn: (documentId: string) => indexingService.deleteDocumentIndex(documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["indexing"] });
      addNotification({
        type: "success",
        title: "Index deleted",
        message: "The document index has been removed",
      });
    },
    onError: (error: Error) => {
      addNotification({
        type: "error",
        title: "Index deletion failed",
        message: error.message,
      });
    },
  });
}

export function useRestoreVersion() {
  const queryClient = useQueryClient();
  const addNotification = useNotificationsStore((s) => s.addNotification);

  return useMutation({
    mutationFn: ({ id, version }: { id: string; version: number }) => restoreVersion(id, version),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.versions(id) });
      queryClient.invalidateQueries({ queryKey: documentKeys.detail(id) });
      addNotification({
        type: "success",
        title: "Version restored",
        message: "The document has been restored to the selected version",
      });
    },
    onError: (error: Error) => {
      addNotification({
        type: "error",
        title: "Restore failed",
        message: error.message,
      });
    },
  });
}
