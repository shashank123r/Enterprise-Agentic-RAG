import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  TrendingUp,
  Search,
  Clock,
  Database,
  HardDrive,
  Activity,
  CheckCircle2,
  AlertCircle,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";
import { Button } from "../components/ui/button";
import { useLayoutStore } from "../store";
import { indexingService } from "../services/indexing.service";
import { healthService } from "../services/health.service";
import { retrievalService } from "../services/retrieval.service";

export function AnalyticsPage() {
  const setPageTitle = useLayoutStore((s) => s.setPageTitle);

  useEffect(() => {
    setPageTitle("Analytics");
  }, [setPageTitle]);

  const { data: indexingStats, isLoading: statsLoading } = useQuery({
    queryKey: ["indexing", "stats"],
    queryFn: () => indexingService.getStats(),
    refetchInterval: 15_000,
  });

  const { data: embeddingHealth } = useQuery({
    queryKey: ["embedding", "health"],
    queryFn: () => healthService.getEmbeddingHealth(),
    refetchInterval: 30_000,
  });

  const { data: vectorHealth } = useQuery({
    queryKey: ["vector-store", "health"],
    queryFn: () => healthService.getVectorStoreHealth(),
    refetchInterval: 30_000,
  });

  const { data: retrievalHealth } = useQuery({
    queryKey: ["retrieval", "health"],
    queryFn: () => retrievalService.getHealth(),
    refetchInterval: 30_000,
  });

  const { data: bm25Status } = useQuery({
    queryKey: ["bm25", "status"],
    queryFn: () => retrievalService.getBM25Status(),
    refetchInterval: 30_000,
  });

  const { data: indexingHealth } = useQuery({
    queryKey: ["indexing", "health"],
    queryFn: () => indexingService.getHealth(),
    refetchInterval: 15_000,
  });

  // Compute derived metrics
  const metrics = useMemo(() => {
    const totalQueries = retrievalHealth?.retrieval_ready ? "Active" : "N/A";
    const avgLatency = embeddingHealth?.latency_ms
      ? `${Math.round(embeddingHealth.latency_ms)}ms`
      : "N/A";
    const totalChunks = indexingStats?.total_chunks_indexed ?? 0;
    const totalVectors = indexingStats?.total_vectors ?? 0;
    const totalCollections = vectorHealth?.collections_count ?? 0;
    const activeJobs = indexingStats?.active_jobs_count ?? 0;
    const completedJobs = indexingStats?.completed_jobs ?? 0;
    const failedJobs = indexingStats?.failed_jobs ?? 0;
    const cacheHitRate = indexingStats?.cache_hit_rate ?? 0;
    const totalFailedChunks = indexingStats?.total_failed_chunks ?? 0;
    const activeTasks = indexingHealth?.task_manager_active_tasks ?? 0;

    return {
      totalQueries,
      avgLatency,
      totalChunks,
      totalVectors,
      totalCollections,
      activeJobs,
      completedJobs,
      failedJobs,
      cacheHitRate,
      totalFailedChunks,
      activeTasks,
    };
  }, [indexingStats, embeddingHealth, vectorHealth, retrievalHealth, indexingHealth]);

  const isLoading = statsLoading;

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-2 h-4 w-64" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-50">Analytics</h1>
          <p className="mt-1 text-sm text-surface-500">Monitor usage and performance metrics</p>
        </div>
        <Badge variant="outline" className="text-[10px] flex items-center gap-1">
          <Activity className="size-3" />
          {embeddingHealth?.healthy ? "Live" : "Offline"}
        </Badge>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <Search className="size-4 text-surface-400" />
              <span className="text-xs text-surface-400">Retrieval</span>
            </div>
            <p className="mt-4 text-2xl font-bold text-surface-900 dark:text-surface-50">{metrics.totalChunks.toLocaleString()}</p>
            <p className="text-sm text-surface-500">Total Chunks Indexed</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <Clock className="size-4 text-surface-400" />
              <span className="text-xs text-surface-400">Avg latency</span>
            </div>
            <p className="mt-4 text-2xl font-bold text-surface-900 dark:text-surface-50">{metrics.avgLatency}</p>
            <p className="text-sm text-surface-500">Embedding Latency</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <Database className="size-4 text-surface-400" />
              <span className="text-xs text-surface-400">Collections</span>
            </div>
            <p className="mt-4 text-2xl font-bold text-surface-900 dark:text-surface-50">{metrics.totalCollections}</p>
            <p className="text-sm text-surface-500">Active Collections</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <HardDrive className="size-4 text-surface-400" />
              <span className="text-xs text-surface-400">Vectors</span>
            </div>
            <p className="mt-4 text-2xl font-bold text-surface-900 dark:text-surface-50">{metrics.totalVectors.toLocaleString()}</p>
            <p className="text-sm text-surface-500">Total Vectors</p>
          </CardContent>
        </Card>
      </div>

      {/* Detailed metrics */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Indexing Performance */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <BarChart3 className="size-4 text-surface-400" />
              Indexing Performance
            </CardTitle>
            <CardDescription>Job completion and error rates</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex items-center justify-between py-2 border-b border-surface-100 dark:border-surface-700">
                <span className="text-sm text-surface-600 dark:text-surface-400">Completed Jobs</span>
                <span className="text-sm font-semibold text-surface-900 dark:text-surface-50">{metrics.completedJobs}</span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-surface-100 dark:border-surface-700">
                <span className="text-sm text-surface-600 dark:text-surface-400">Active Jobs</span>
                <span className="text-sm font-semibold text-surface-900 dark:text-surface-50">{metrics.activeJobs}</span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-surface-100 dark:border-surface-700">
                <span className="text-sm text-surface-600 dark:text-surface-400">Failed Jobs</span>
                <span className={`text-sm font-semibold ${metrics.failedJobs > 0 ? "text-red-600 dark:text-red-400" : "text-surface-900 dark:text-surface-50"}`}>
                  {metrics.failedJobs}
                </span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-surface-100 dark:border-surface-700">
                <span className="text-sm text-surface-600 dark:text-surface-400">Failed Chunks</span>
                <span className={`text-sm font-semibold ${metrics.totalFailedChunks > 0 ? "text-amber-600" : "text-surface-900 dark:text-surface-50"}`}>
                  {metrics.totalFailedChunks}
                </span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-surface-100 dark:border-surface-700">
                <span className="text-sm text-surface-600 dark:text-surface-400">Cache Hit Rate</span>
                <span className="text-sm font-semibold text-surface-900 dark:text-surface-50">
                  {(metrics.cacheHitRate * 100).toFixed(1)}%
                </span>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-sm text-surface-600 dark:text-surface-400">Active Background Tasks</span>
                <span className="text-sm font-semibold text-surface-900 dark:text-surface-50">{metrics.activeTasks}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* System Health */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <Activity className="size-4 text-surface-400" />
              System Health
            </CardTitle>
            <CardDescription>Component status overview</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex items-center justify-between py-2 border-b border-surface-100 dark:border-surface-700">
                <span className="text-sm text-surface-600 dark:text-surface-400">Embedding Provider</span>
                <Badge variant={embeddingHealth?.healthy ? "success" : "destructive"} className="text-[10px]">
                  {embeddingHealth?.healthy ? "Healthy" : "Unhealthy"}
                </Badge>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-surface-100 dark:border-surface-700">
                <span className="text-sm text-surface-600 dark:text-surface-400">Vector Store (Milvus)</span>
                <Badge variant={vectorHealth?.healthy ? "success" : "destructive"} className="text-[10px]">
                  {vectorHealth?.healthy ? "Connected" : "Disconnected"}
                </Badge>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-surface-100 dark:border-surface-700">
                <span className="text-sm text-surface-600 dark:text-surface-400">BM25 Index</span>
                <Badge variant={bm25Status?.healthy ? "success" : "warning"} className="text-[10px]">
                  {bm25Status?.healthy ? "Built" : "Not Built"}
                </Badge>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-surface-100 dark:border-surface-700">
                <span className="text-sm text-surface-600 dark:text-surface-400">Retrieval System</span>
                <Badge variant={retrievalHealth?.retrieval_ready ? "success" : "warning"} className="text-[10px]">
                  {retrievalHealth?.retrieval_ready ? "Ready" : "Degraded"}
                </Badge>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-sm text-surface-600 dark:text-surface-400">Embedding Model</span>
                <span className="text-xs font-mono text-surface-500">{embeddingHealth?.model ?? "N/A"}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Additional stats */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <Database className="size-4 text-surface-400" />
            Knowledge Base Summary
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            <div>
              <p className="text-xs text-surface-400">Total Documents</p>
              <p className="text-lg font-bold text-surface-900 dark:text-surface-50">--</p>
              <p className="text-[10px] text-surface-400">Queries documents endpoint</p>
            </div>
            <div>
              <p className="text-xs text-surface-400">Indexed Chunks</p>
              <p className="text-lg font-bold text-surface-900 dark:text-surface-50">{metrics.totalChunks.toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-surface-400">Total Vectors in Milvus</p>
              <p className="text-lg font-bold text-surface-900 dark:text-surface-50">{metrics.totalVectors.toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-surface-400">Collections</p>
              <p className="text-lg font-bold text-surface-900 dark:text-surface-50">{metrics.totalCollections}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
