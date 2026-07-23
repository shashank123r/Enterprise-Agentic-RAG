import apiClient, { getStoredTokens } from "./api";
import type { RAGRequest, RAGResponse } from "../types";

export const ragService = {
  async chat(request: RAGRequest): Promise<RAGResponse> {
    const { data } = await apiClient.post<RAGResponse>("/chat", request);
    return data;
  },

  async *chatStream(
    request: RAGRequest,
  ): AsyncGenerator<
    { type: "token"; content: string } | { type: "metadata"; data: Record<string, unknown> } | { type: "error"; message: string } | { type: "done" }
  > {
    const tokens = getStoredTokens();
    const response = await fetch(
      `${apiClient.defaults.baseURL}/chat/stream`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${tokens?.access_token ?? ""}`,
        },
        body: JSON.stringify(request),
      },
    );

    if (!response.ok) {
      yield { type: "error", message: `HTTP ${response.status}: ${response.statusText}` };
      return;
    }

    const reader = response.body?.getReader();
    if (!reader) {
      yield { type: "error", message: "No response body" };
      return;
    }

    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") {
            yield { type: "done" };
            return;
          }
          try {
            const parsed = JSON.parse(payload);
            if (parsed.type === "token") {
              yield { type: "token", content: parsed.content };
            } else if (parsed.type === "metadata") {
              yield { type: "metadata", data: parsed };
            } else if (parsed.type === "error") {
              yield { type: "error", message: parsed.message };
            } else {
              yield { type: "token", content: payload };
            }
          } catch {
            // Non-JSON data, pass through as token
            yield { type: "token", content: payload };
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  },

  async validate(request: {
    question: string;
    answer: string;
    chunks: Array<{
      chunk_id: string;
      document_id: string;
      text_preview: string;
      score: number;
      page_number: number | null;
      section_title: string | null;
      document_title: string;
    }>;
  }): Promise<{ grounding_valid: boolean; issues: string[] }> {
    const { data } = await apiClient.post("/chat/validate", request);
    return data;
  },
};
