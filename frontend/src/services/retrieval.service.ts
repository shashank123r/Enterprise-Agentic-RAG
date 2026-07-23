import apiClient from "./api";
import type {
  RetrievalRequest,
  RetrievalResult,
  BM25Status,
  RetrievalHealth,
} from "../types";

export const retrievalService = {
  async search(request: RetrievalRequest): Promise<RetrievalResult> {
    const { data } = await apiClient.post<RetrievalResult>(
      "/retrieval/search",
      request,
    );
    return data;
  },

  async searchDense(
    query: string,
    topK = 10,
    collectionName = "documents",
  ): Promise<RetrievalResult> {
    const { data } = await apiClient.post<RetrievalResult>(
      "/retrieval/search/dense",
      null,
      {
        params: { query, top_k: topK, collection_name: collectionName },
      },
    );
    return data;
  },

  async searchHybrid(
    query: string,
    topK = 10,
    alpha = 0.5,
    collectionName = "documents",
  ): Promise<RetrievalResult> {
    const { data } = await apiClient.post<RetrievalResult>(
      "/retrieval/search/hybrid",
      null,
      {
        params: {
          query,
          top_k: topK,
          alpha,
          collection_name: collectionName,
        },
      },
    );
    return data;
  },

  async buildBM25Index(): Promise<{ status: string; total_docs?: number; unique_tokens?: number }> {
    const { data } = await apiClient.post("/retrieval/bm25/build-index");
    return data;
  },

  async rebuildBM25Index(): Promise<{ status: string }> {
    const { data } = await apiClient.post("/retrieval/bm25/rebuild");
    return data;
  },

  async getBM25Status(): Promise<BM25Status> {
    const { data } = await apiClient.get<BM25Status>("/retrieval/bm25/status");
    return data;
  },

  async clearBM25Index(): Promise<void> {
    await apiClient.delete("/retrieval/bm25");
  },

  async getMethods(): Promise<{ methods: string[]; default: string; bm25_index_built: boolean }> {
    const { data } = await apiClient.get("/retrieval/methods");
    return data;
  },

  async getHealth(): Promise<RetrievalHealth> {
    const { data } = await apiClient.get<RetrievalHealth>("/retrieval/health");
    return data;
  },
};
