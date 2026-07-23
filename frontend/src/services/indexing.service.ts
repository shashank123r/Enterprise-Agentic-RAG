import apiClient from "./api";
import type {
  IndexingJob,
  IndexingStartResponse,
  IndexingHealth,
  IndexingStats,
  EmbeddingHealth,
  VectorStoreHealth,
} from "../types";

export const indexingService = {
  async startIndexing(
    documentId: string,
    collectionName = "documents",
    useArq = false,
  ): Promise<IndexingStartResponse> {
    const { data } = await apiClient.post<IndexingStartResponse>(
      `/indexing/start`,
      null,
      {
        params: {
          document_id: documentId,
          collection_name: collectionName,
          use_arq: useArq,
        },
      },
    );
    return data;
  },

  async getJobStatus(jobId: string): Promise<IndexingJob> {
    const { data } = await apiClient.get<IndexingJob>(`/indexing/${jobId}`);
    return data;
  },

  async listJobs(documentId?: string, limit = 20): Promise<IndexingJob[]> {
    const { data } = await apiClient.get<IndexingJob[]>(`/indexing/`, {
      params: { document_id: documentId, limit },
    });
    return data;
  },

  async cancelJob(jobId: string): Promise<void> {
    await apiClient.post(`/indexing/${jobId}/cancel`);
  },

  async retryJob(jobId: string): Promise<void> {
    await apiClient.post(`/indexing/${jobId}/retry`);
  },

  async rebuildIndex(
    documentId: string,
    collectionName = "documents",
    useArq = false,
  ): Promise<{ job_id: string; status: string }> {
    const { data } = await apiClient.post(`/indexing/rebuild`, null, {
      params: {
        document_id: documentId,
        collection_name: collectionName,
        use_arq: useArq,
      },
    });
    return data;
  },

  async deleteDocumentIndex(
    documentId: string,
    collectionName = "documents",
  ): Promise<{ vectors_deleted: number }> {
    const { data } = await apiClient.delete(`/indexing/documents/${documentId}`, {
      params: { collection_name: collectionName },
    });
    return data;
  },

  async getStats(): Promise<IndexingStats> {
    const { data } = await apiClient.get<IndexingStats>(`/indexing/stats/summary`);
    return data;
  },

  async getHealth(): Promise<IndexingHealth> {
    const { data } = await apiClient.get<IndexingHealth>(`/indexing/health`);
    return data;
  },

  async getEmbeddingHealth(): Promise<EmbeddingHealth> {
    const { data } = await apiClient.get<EmbeddingHealth>(`/indexing/health/embedding`);
    return data;
  },

  async getVectorStoreHealth(): Promise<VectorStoreHealth> {
    const { data } = await apiClient.get<VectorStoreHealth>(`/indexing/health/vector-store`);
    return data;
  },
};
