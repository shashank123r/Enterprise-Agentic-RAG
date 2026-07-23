import apiClient from "./api";
import type { HealthCheck, EmbeddingHealth, VectorStoreHealth } from "../types";

export const healthService = {
  async getLive(): Promise<{ message: string; code: string }> {
    const { data } = await apiClient.get("/health/live");
    return data;
  },

  async getReady(): Promise<HealthCheck> {
    const { data } = await apiClient.get<HealthCheck>("/health/ready");
    return data;
  },

  async getFull(): Promise<HealthCheck> {
    const { data } = await apiClient.get<HealthCheck>("/health");
    return data;
  },

  async getEmbeddingHealth(): Promise<EmbeddingHealth> {
    const { data } = await apiClient.get<EmbeddingHealth>("/indexing/health/embedding");
    return data;
  },

  async getVectorStoreHealth(): Promise<VectorStoreHealth> {
    const { data } = await apiClient.get<VectorStoreHealth>("/indexing/health/vector-store");
    return data;
  },
};
