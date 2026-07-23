import { useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Database,
  HardDrive,
  Layers,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";
import { Button } from "../components/ui/button";
import { useLayoutStore } from "../store";
import { healthService } from "../services/health.service";
import { retrievalService } from "../services/retrieval.service";
import { indexingService } from "../services/indexing.service";

export function CollectionsPage() {
  const navigate = useNavigate();
  const setPageTitle = useLayoutStore((s) => s.setPageTitle);

  useEffect(() => {
    setPageTitle("Collections");
  }, [setPageTitle]);

  const { data: vectorHealth, isLoading: vsLoading, error: vsError } = useQuery({
    queryKey: ["vector-store", "health"],
    queryFn: () => healthService.getVectorStoreHealth(),
    refetchInterval: 15_000,
  });

  const { data: embeddingHealth } = useQuery({
    queryKey: ["embedding", "health"],
    queryFn: () => healthService.getEmbeddingHealth(),
  });

  const { data: bm25Status } = useQuery({
    queryKey: ["bm25", "status"],
    queryFn: () => retrievalService.getBM25Status(),
  });

  const { data: indexingStats } = useQuery({
    queryKey: ["indexing", "stats"],
    queryFn: () => indexingService.getStats(),
  });

  const isLoading = vsLoading;

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <div>
          <Skeleton className="h-8 w-48" />
          <Skeleton className="mt-2 h-4 w-64" />
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-5">
                <Skeleton className="size-10 rounded-lg" />
                <Skeleton className="mt-3 h-5 w-32" />
                <Skeleton className="mt-3 h-4 w-full" />
                <Skeleton className="mt-2 h-4 w-3/4" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  if (vsError || !vectorHealth?.healthy) {
    return (
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-50">Collections</h1>
          <p className="mt-1 text-sm text-surface-500">Manage vector collections and embeddings</p>
        </div>
        <Card>
          <CardContent className="flex flex-col items-center py-12 text-center">
            <AlertCircle className="mb-3 size-10 text-red-400" />
            <h3 className="text-sm font-medium text-surface-900 dark:text-surface-100">Vector Store Unavailable</h3>
            <p className="mt-1 text-xs text-surface-500 max-w-sm">
              Milvus is not responding. Collection management requires a healthy vector store connection.
            </p>
            <Button variant="outline" size="sm" className="mt-4" onClick={() => window.location.reload()}>
              <RefreshCw className="mr-1.5 size-3.5" />
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const collections = vectorHealth?.collections ?? [];
  const isHealthy = vectorHealth?.healthy ?? false;
  const totalVectors = indexingStats?.total_vectors ?? 0;
  const totalChunksIndexed = indexingStats?.total_chunks_indexed ?? 0;
  const cacheHitRate = indexingStats?.cache_hit_rate ?? 0;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-50">Collections</h1>
          <p className="mt-1 text-sm text-surface-500">Manage vector collections and embeddings</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={isHealthy ? "success" : "destructive"} className="text-[10px]">
            {isHealthy ? "Connected" : "Disconnected"}
          </Badge>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="p-5">
            <div className="rounded-lg bg-purple-50 p-2 text-purple-600 w-fit dark:bg-purple-950 dark:text-purple-400">
              <Database className="size-5" />
            </div>
            <p className="mt-4 text-2xl font-bold text-surface-900 dark:text-surface-50">{collections.length}</p>
            <p className="text-sm text-surface-500">Collections</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="rounded-lg bg-blue-50 p-2 text-blue-600 w-fit dark:bg-blue-950 dark:text-blue-400">
              <HardDrive className="size-5" />
            </div>
            <p className="mt-4 text-2xl font-bold text-surface-900 dark:text-surface-50">{totalChunksIndexed.toLocaleString()}</p>
            <p className="text-sm text-surface-500">Indexed Chunks</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="rounded-lg bg-green-50 p-2 text-green-600 w-fit dark:bg-green-950 dark:text-green-400">
              <Layers className="size-5" />
            </div>
            <p className="mt-4 text-2xl font-bold text-surface-900 dark:text-surface-50">{totalVectors.toLocaleString()}</p>
            <p className="text-sm text-surface-500">Total Vectors</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="rounded-lg bg-amber-50 p-2 text-amber-600 w-fit dark:bg-amber-950 dark:text-amber-400">
              <Database className="size-5" />
            </div>
            <p className="mt-4 text-2xl font-bold text-surface-900 dark:text-surface-50">{(cacheHitRate * 100).toFixed(1)}%</p>
            <p className="text-sm text-surface-500">Cache Hit Rate</p>
          </CardContent>
        </Card>
      </div>

      {/* Collection cards */}
      {collections.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {collections.map((name) => (
            <Card key={name} className="hover:shadow-card-hover transition-all">
              <CardContent className="p-5">
                <div className="flex items-start justify-between mb-4">
                  <div className="rounded-lg bg-purple-50 p-2 text-purple-600 dark:bg-purple-950 dark:text-purple-400">
                    <Database className="size-5" />
                  </div>
                  <Badge variant="success" className="text-[10px]">active</Badge>
                </div>
                <h3 className="font-semibold text-surface-900 dark:text-surface-50 text-sm">{name}</h3>
                <div className="mt-3 space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-surface-400">Embedding Model</span>
                    <span className="font-medium text-surface-700 dark:text-surface-300">
                      {embeddingHealth?.model ?? "N/A"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-surface-400">Vector Dimension</span>
                    <span className="font-medium text-surface-700 dark:text-surface-300">
                      {vectorHealth?.collections_count ? "4096" : "N/A"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-surface-400">BM25 Index</span>
                    <span className="font-medium">
                      {bm25Status?.healthy ? (
                        <span className="text-green-600 dark:text-green-400">Built ({bm25Status.total_docs} docs)</span>
                      ) : (
                        <span className="text-amber-600 dark:text-amber-400">Not built</span>
                      )}
                    </span>
                  </div>
                </div>
                <div className="mt-4 flex items-center justify-between border-t border-surface-100 pt-3 dark:border-surface-700">
                  <span className="text-[10px] text-surface-400">Provider: Milvus</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center py-16 text-center">
            <Database className="mb-3 size-10 text-surface-300 dark:text-surface-600" />
            <h3 className="text-sm font-medium text-surface-900 dark:text-surface-100">No Collections</h3>
            <p className="mt-1 text-xs text-surface-500 max-w-xs">
              Collections are created automatically when documents are indexed. Upload and index a document to create your first collection.
            </p>
            <Button variant="outline" size="sm" className="mt-4" onClick={() => navigate("/documents")}>
              Go to Documents
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
