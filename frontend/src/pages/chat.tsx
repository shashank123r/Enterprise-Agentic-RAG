import { useEffect, useRef, useState, useCallback } from "react";
import { Send, Sparkles, BookOpen, Copy, Check, Loader2 } from "lucide-react";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { useLayoutStore } from "../store";
import { ragService } from "../services/rag.service";
import type { RAGRequest, CitationInfo, RAGChunk } from "../types";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: CitationInfo[];
  chunks?: RAGChunk[];
  grounding_valid?: boolean;
  duration_ms?: number;
}

export function ChatPage() {
  const setPageTitle = useLayoutStore((s) => s.setPageTitle);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setPageTitle("Chat");
  }, [setPageTitle]);

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleSend = useCallback(async () => {
    if (!input.trim() || isStreaming) return;

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content: input.trim(),
    };

    const assistantMessage: Message = {
      id: `assistant-${Date.now()}`,
      role: "assistant",
      content: "",
    };

    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setInput("");
    setIsStreaming(true);

    try {
      // Only include completed messages (exclude the in-progress assistant placeholder)
      const completedHistory = messages.filter((m) => m.content.length > 0);
      const request: RAGRequest = {
        question: userMessage.content,
        collection_name: "documents",
        top_k: 5,
        retrieval_method: "hybrid",
        rerank: true,
        query_rewrite: true,
        max_context_tokens: 4096,
        max_response_tokens: 1024,
        temperature: 0.1,
        stream: true,
        conversation_history: completedHistory.slice(-6).map((m) => ({
          role: m.role,
          content: m.content,
        })),
      };

      let fullContent = "";
      let finalCitations: CitationInfo[] = [];
      let finalChunks: RAGChunk[] = [];
      let groundingValid = true;
      let totalDuration = 0;

      for await (const event of ragService.chatStream(request)) {
        if (event.type === "token") {
          fullContent += event.content;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMessage.id ? { ...m, content: fullContent } : m,
            ),
          );
        } else if (event.type === "metadata") {
          finalCitations = event.data.citations ?? [];
          finalChunks = event.data.chunks ?? [];
          groundingValid = event.data.grounding_valid ?? true;
          totalDuration = event.data.total_duration_ms ?? 0;
        } else if (event.type === "error") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMessage.id
                ? { ...m, content: `Error: ${event.message}` }
                : m,
            ),
          );
        }
      }

      // Update with final metadata
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMessage.id
            ? {
                ...m,
                citations: finalCitations,
                chunks: finalChunks,
                grounding_valid: groundingValid,
                duration_ms: totalDuration,
              }
            : m,
        ),
      );
    } catch (error) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMessage.id
            ? { ...m, content: `Error: ${(error as Error).message}` }
            : m,
        ),
      );
    } finally {
      setIsStreaming(false);
      inputRef.current?.focus();
    }
  }, [input, isStreaming, messages]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleCopy = useCallback(async (id: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      // Ignore clipboard errors
    }
  }, []);

  const handleSuggestion = useCallback(
    (text: string) => {
      setInput(text);
      inputRef.current?.focus();
    },
    [],
  );

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4">
        <div className="mx-auto max-w-3xl py-8">
          {messages.length === 0 ? (
            <>
              {/* Welcome */}
              <div className="mb-8 text-center">
                <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-xl bg-brand-600 shadow-lg">
                  <Sparkles className="size-6 text-white" />
                </div>
                <h2 className="text-lg font-semibold text-surface-900 dark:text-surface-50">
                  How can I help you today?
                </h2>
                <p className="mt-1 text-sm text-surface-500">
                  Ask questions about your enterprise knowledge base
                </p>
              </div>

              {/* Suggestions */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {[
                  "Summarize the key architecture components of the RAG platform",
                  "What are the main features of the document ingestion pipeline?",
                  "How does the hybrid search work?",
                  "What embedding models are supported?",
                ].map((text) => (
                  <button
                    key={text}
                    onClick={() => handleSuggestion(text)}
                    className="rounded-lg border border-surface-200 bg-white p-4 text-left text-sm text-surface-600 hover:border-brand-300 hover:text-surface-900 transition-all dark:border-surface-700 dark:bg-surface-800 dark:text-surface-400 dark:hover:border-brand-600 dark:hover:text-surface-200"
                  >
                    <BookOpen className="mb-2 size-4 text-brand-600 dark:text-brand-400" />
                    {text}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <div className="flex flex-col gap-4">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-3 ${msg.role === "assistant" ? "" : "flex-row-reverse"}`}
                >
                  {/* Avatar */}
                  <div
                    className={`shrink-0 size-8 rounded-lg flex items-center justify-center text-xs font-bold ${
                      msg.role === "assistant"
                        ? "bg-brand-600 text-white"
                        : "bg-surface-200 text-surface-600 dark:bg-surface-700 dark:text-surface-300"
                    }`}
                  >
                    {msg.role === "assistant" ? "AI" : "U"}
                  </div>

                  {/* Content */}
                  <div className={`max-w-[80%] ${msg.role === "assistant" ? "" : "items-end flex flex-col"}`}>
                    <div
                      className={`rounded-xl px-4 py-3 ${
                        msg.role === "assistant"
                          ? "bg-white border border-surface-200 dark:bg-surface-800 dark:border-surface-700"
                          : "bg-brand-600 text-white"
                      }`}
                    >
                      <p className="text-sm whitespace-pre-wrap leading-relaxed">
                        {msg.content || (isStreaming && msg.role === "assistant" ? "..." : "")}
                      </p>
                    </div>

                    {/* Citations */}
                    {msg.citations && msg.citations.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {msg.citations.map((cit, i) => (
                          <Badge
                            key={i}
                            variant="outline"
                            className="text-[10px] flex items-center gap-1"
                            title={cit.text_preview}
                          >
                            <BookOpen className="size-3" />
                            {cit.document_title || `Source ${cit.index}`}
                            {cit.page_number && ` (p.${cit.page_number})`}
                          </Badge>
                        ))}
                      </div>
                    )}

                    {/* Grounding + Actions */}
                    {msg.role === "assistant" && msg.content && (
                      <div className="mt-1.5 flex items-center gap-2">
                        {msg.grounding_valid !== undefined && (
                          <span
                            className={`text-[10px] ${
                              msg.grounding_valid
                                ? "text-green-600 dark:text-green-400"
                                : "text-amber-600 dark:text-amber-400"
                            }`}
                          >
                            {msg.grounding_valid ? "✓ Grounded" : "⚠ Unverified"}
                          </span>
                        )}
                        {msg.duration_ms && (
                          <span className="text-[10px] text-surface-400">
                            {(msg.duration_ms / 1000).toFixed(1)}s
                          </span>
                        )}
                        <button
                          onClick={() => handleCopy(msg.id, msg.content)}
                          className="p-1 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300"
                          title="Copy response"
                          aria-label="Copy response to clipboard"
                        >
                          {copiedId === msg.id ? (
                            <Check className="size-3 text-green-500" />
                          ) : (
                            <Copy className="size-3" />
                          )}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* Input area */}
      <div className="border-t border-surface-200 bg-white p-4 dark:border-surface-700 dark:bg-surface-800">
        <div className="mx-auto flex max-w-3xl items-end gap-3">
          <div className="relative flex-1">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about your documents..."
              className="min-h-[44px] w-full resize-none rounded-xl border border-surface-300 bg-surface-50 px-4 py-3 text-sm text-surface-900 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-surface-600 dark:bg-surface-900 dark:text-surface-100"
              rows={1}
              disabled={isStreaming}
              onInput={(e) => {
                const target = e.currentTarget;
                target.style.height = "auto";
                target.style.height = `${Math.min(target.scrollHeight, 200)}px`;
              }}
            />
          </div>
          <Button
            className="h-11 shrink-0 rounded-xl px-4"
            onClick={handleSend}
            disabled={!input.trim() || isStreaming}
          >
            {isStreaming ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Send className="size-4" />
            )}
          </Button>
        </div>
        <p className="mx-auto mt-2 max-w-3xl text-center text-[10px] text-surface-400">
          Responses are grounded in your uploaded documents. Verify important information.
        </p>
      </div>
    </div>
  );
}
