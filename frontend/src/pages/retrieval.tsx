import { useEffect, useState, useCallback } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  Search,
  SlidersHorizontal,
  BookOpen,
  Clock,
  Layers,
  FileText,
  AlertCircle,
  RefreshCw,
  Loader2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { useLayoutStore } from "../store";
import { retrievalService } from "../services/retrieval.service";
import type { RetrievalMethod, RetrievalResult, RetrievedChunk } from "../types";

export function RetrievalPage() {
  const setPageTitle = useLayoutStore((s) => s.setPageTitle);

  useEffect(() => {
    setPageTitle("Retrieval");
  }, [setPageTitle]);

  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [method, setMethod] = useState<RetrievalMethod>("dense");
  const [rerank, setRerank] = useState(false);
  const [result, setResult] = useState<RetrievalResult | null>(null);
  const [expandedChunk, setExpandedChunk] = useState<string | null>(null);

  const searchMutation = useMutation({
    mutationFn: () =>
      retrievalService.search({
        query,
        top_k: topK,
        method,
        rerank,
        collection_name: "documents",
      }),
    onSuccess: (data) => setResult(data),
  });

  const handleSearch = useCallback(() => {
    if (!query.trim()) return;
    searchMutation.mutate();
  }, [query, searchMutation]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSearch();
      }
    },
    [handleSearch],
  );

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-50">Retrieval Playground</h1>
          <p className="mt-1 text-sm text-surface-500">Test and tune your retrieval pipeline</p>
        </div>
      </div>

      {/* Search bar */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-surface-400" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder='Search your knowledge base (e.g., "What is the RAG platform architecture?")'
                className="w-full h-10 pl-10 pr-4 rounded-lg border border-surface-300 bg-surface-50 text-sm text-surface-900 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-surface-600 dark:bg-surface-900 dark:text-surface-100"
                autoFocus
              />
            </div>
            <div className="flex items-center gap-2">
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value as RetrievalMethod)}
                className="h-10 rounded-lg border border-surface-300 bg-surface-50 px-3 text-xs text-surface-700 focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-surface-600 dark:bg-surface-900 dark:text-surface-300"
              >
                <option value="dense">Dense</option>
                <option value="bm25">BM25</option>
                <option value="hybrid">Hybrid</option>
              </select>
              <select
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
                className="h-10 rounded-lg border border-surface-300 bg-surface-50 px-3 text-xs text-surface-700 focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-surface-600 dark:bg-surface-900 dark:text-surface-300"
              >
                {[3, 5, 10, 20].map((n) => (
                  <option key={n} value={n}>Top {n}</option>
                ))}
              </select>
              <label className="flex items-center gap-1.5 text-xs text-surface-600 dark:text-surface-400 cursor-pointer">
                <input
                  type="checkbox"
                  checked={rerank}
                  onChange={(e) => setRerank(e.target.checked)}
                  className="rounded border-surface-300"
                />
                Rerank
              </label>
              <Button
                size="sm"
                onClick={handleSearch}
                disabled={searchMutation.isPending || !query.trim()}
              >
                {searchMutation.isPending ? (
                  <Loader2 className="size-3.5 animate-spin mr-1" />
                ) : (
                  <Search className="size-3.5 mr-1" />
                )}
                Search
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Result area */}
      {searchMutation.isPending && (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-32 rounded-xl" />
          ))}
        </div>
      )}

      {searchMutation.error && (
        <Card>
          <CardContent className="flex flex-col items-center py-12 text-center">
            <AlertCircle className="mb-3 size-10 text-red-400" />
            <h3 className="text-sm font-medium text-surface-900 dark:text-surface-100">Search Failed</h3>
            <p className="mt-1 text-xs text-surface-500 max-w-md">
              {(searchMutation.error as Error).message}
            </p>
            <Button variant="outline" size="sm" className="mt-4" onClick={handleSearch}>
              <RefreshCw className="mr-1.5 size-3.5" />
              Retry
            </Button>
          </CardContent>
        </Card>
      )}

      {result && !searchMutation.isPending && (
        <div className="space-y-4">
          {/* Result metadata */}
          <div className="flex items-center gap-4 text-xs text-surface-500">
            <span className="flex items-center gap-1">
              <Layers className="size-3.5" />
              {result.total_results} results
            </span>
            <span className="flex items-center gap-1">
              <Clock className="size-3.5" />
              {result.metrics.total_duration_ms.toFixed(0)}ms
            </span>
            <span className="flex items-center gap-1">
              <FileText className="size-3.5" />
              Method: {result.method}
            </span>
            {result.rewritten_query && (
              <span className="text-surface-400 italic">
                Rewritten: "{result.rewritten_query}"
              </span>
            )}
          </div>

          {/* Result chunks */}
          <div className="space-y-3">
            {result.chunks.map((chunk: RetrievedChunk, index: number) => (
              <Card
                key={`${chunk.chunk_id}-${index}`}
                className="hover:shadow-card-hover transition-shadow cursor-pointer"
                onClick={() =>
                  setExpandedChunk(expandedChunk === `${chunk.chunk_id}-${index}` ? null : `${chunk.chunk_id}-${index}`)
                }
              >
                <CardContent className="p-4">
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-[10px]">
                        #{index + 1}
                      </Badge>
                      <Badge variant="outline" className="text-[10px]">
                        {chunk.retrieval_source}
                      </Badge>
                      {chunk.page_number && (
                        <span className="text-[10px] text-surface-400">Page {chunk.page_number}</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono text-surface-500">
                        score: {chunk.score.toFixed(4)}
                      </span>
                      {chunk.rerank_score !== null && (
                        <span className="text-xs font-mono text-brand-600">
                          rerank: {chunk.rerank_score!.toFixed(4)}
                        </span>
                      )}
                    </div>
                  </div>
                  <p className="text-sm text-surface-700 dark:text-surface-300 leading-relaxed whitespace-pre-wrap">
                    {expandedChunk === `${chunk.chunk_id}-${index}`
                      ? chunk.text
                      : chunk.text.length > 300
                        ? `${chunk.text.slice(0, 300)}...`
                        : chunk.text}
                  </p>
                  {chunk.text.length > 300 && (
                    <button className="mt-2 text-xs text-brand-600 hover:text-brand-700 dark:text-brand-400">
                      {expandedChunk === `${chunk.chunk_id}-${index}` ? "Show less" : "Show more"}
                    </button>
                  )}
                  {chunk.section_title && (
                    <div className="mt-2 flex items-center gap-1 text-[10px] text-surface-400">
                      <BookOpen className="size-3" />
                      {chunk.section_title}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!result && !searchMutation.isPending && !searchMutation.error && (
        <Card>
          <CardContent className="flex flex-col items-center py-16 text-center">
            <BookOpen className="mb-3 size-10 text-surface-300 dark:text-surface-600" />
            <h3 className="text-sm font-medium text-surface-900 dark:text-surface-100">No search results yet</h3>
            <p className="mt-1 text-xs text-surface-500 max-w-xs">
              Enter a query above to search across your indexed documents using dense, BM25, or hybrid retrieval.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
