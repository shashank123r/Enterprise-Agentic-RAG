import { useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  FileText,
  Database,
  HardDrive,
  Search,
  Clock,
  Sparkles,
  AlertCircle,
  CheckCircle2,
  Loader2,
  Activity,
  BarChart3,
  Upload,
  BookOpen,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";
import { Button } from "../components/ui/button";
import { useLayoutStore } from "../store";
import { useDocumentsList } from "../hooks/useDocuments";
import { indexingService } from "../services/indexing.service";
import { retrievalService } from "../services/retrieval.service";
import { healthService } from "../services/health.service";

export function DashboardPage() {
  const navigate = useNavigate();
  const setPageTitle = useLayoutStore((s) => s.setPageTitle);

  useEffect(() => {
    setPageTitle("Dashboard");
  }, [setPageTitle]);

  // ── Real API Queries ─────────────────────

  const { data: docsData, isLoading: docsLoading } = useDocumentsList({
    page: 1,
    page_size: 1,
  });

  const { data: documents, isLoading: recentDocsLoading } = useDocumentsList({
    page: 1,
    page_size: 5,
    sort_by: "created_at",
    sort_order: "desc",
  });

  const { data: indexingStats, isLoading: statsLoading } = useQuery({
    queryKey: ["indexing", "stats"],
    queryFn: () => indexingService.getStats(),
    refetchInterval: 10_000,
  });

  const { data: vectorHealth, isLoading: vsLoading } = useQuery({
    queryKey: ["vector-store", "health"],
    queryFn: () => healthService.getVectorStoreHealth(),
  });

  const { data: embeddingHealth, isLoading: embLoading } = useQuery({
    queryKey: ["embedding", "health"],
    queryFn: () => healthService.getEmbeddingHealth(),
  });

  const { data: retrievalHealth, isLoading: retLoading } = useQuery({
    queryKey: ["retrieval", "health"],
    queryFn: () => retrievalService.getHealth(),
  });

  const { data: indexingJobs } = useQuery({
    queryKey: ["indexing", "jobs"],
    queryFn: () => indexingService.listJobs(undefined, 5),
    refetchInterval: 10_000,
  });

  const isLoading = docsLoading || statsLoading || vsLoading || embLoading || retLoading;

  // ── Derived Stats ─────────────────────────

  const stats = useMemo(() => {
    const totalDocs = docsData?.total ?? 0;
    const totalChunks = indexingStats?.total_chunks_indexed ?? 0;
    const activeJobs = indexingStats?.active_jobs_count ?? 0;
    const collections = vectorHealth?.collections_count ?? 0;
    const embModel = embeddingHealth?.model ?? "N/A";
    const latencyMs = embeddingHealth?.latency_ms ?? 0;
    const retLatency = retrievalHealth?.vector_store?.healthy
      ? `${Math.round(latencyMs)}ms`
      : "N/A";
    const dbHealthy = retrievalHealth?.vector_store?.healthy ?? false;

    return {
      totalDocs,
      totalChunks,
      activeJobs,
      collections,
      embModel,
      retLatency,
      dbHealthy,
      failedJobs: indexingStats?.counts_by_status?.failed ?? 0,
      completedJobs: indexingStats?.counts_by_status?.completed ?? 0,
    };
  }, [docsData, indexingStats, vectorHealth, embeddingHealth, retrievalHealth]);

  // ── Status Badge Helper ───────────────────

  function StatusBadge({ status }: { status: string }) {
    const variants: Record<string, { variant: "success" | "warning" | "destructive" | "outline"; label: string }> = {
      completed: { variant: "success", label: "Completed" },
      processing: { variant: "warning", label: "Processing" },
      pending: { variant: "outline", label: "Pending" },
      failed: { variant: "destructive", label: "Failed" },
      queued: { variant: "outline", label: "Queued" },
    };
    const v = variants[status] ?? { variant: "outline" as const, label: status };
    return <Badge variant={v.variant} className="text-[10px]">{v.label}</Badge>;
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <div>
          <Skeleton className="h-8 w-48" />
          <Skeleton className="mt-2 h-4 w-72" />
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-5">
                <Skeleton className="size-10 rounded-lg" />
                <Skeleton className="mt-4 h-8 w-20" />
                <Skeleton className="mt-1 h-4 w-24" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-50">
            Dashboard
          </h1>
          <p className="mt-1 text-sm text-surface-500 dark:text-surface-400">
            Overview of your enterprise knowledge base
          </p>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Documents */}
        <Card className="hover:shadow-card-hover transition-shadow">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div className="rounded-lg bg-brand-50 p-2 text-brand-600 dark:bg-brand-950 dark:text-brand-400">
                <FileText className="size-5" />
              </div>
              {stats.completedJobs > 0 && (
                <div className="flex items-center gap-1 rounded-full bg-green-50 px-2 py-0.5 text-[10px] font-medium text-green-700 dark:bg-green-950 dark:text-green-400">
                  <CheckCircle2 className="size-3" />
                  {stats.completedJobs} done
                </div>
              )}
            </div>
            <p className="mt-4 text-2xl font-bold text-surface-900 dark:text-surface-50">
              {stats.totalDocs}
            </p>
            <p className="mt-0.5 text-sm text-surface-500 dark:text-surface-400">
              Total Documents
            </p>
          </CardContent>
        </Card>

        {/* Collections */}
        <Card className="hover:shadow-card-hover transition-shadow">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div className="rounded-lg bg-purple-50 p-2 text-purple-600 dark:bg-purple-950 dark:text-purple-400">
                <Database className="size-5" />
              </div>
              <Badge variant={stats.dbHealthy ? "success" : "destructive"} className="text-[10px]">
                {stats.dbHealthy ? "Connected" : "Disconnected"}
              </Badge>
            </div>
            <p className="mt-4 text-2xl font-bold text-surface-900 dark:text-surface-50">
              {stats.collections}
            </p>
            <p className="mt-0.5 text-sm text-surface-500 dark:text-surface-400">
              Collections
            </p>
            {stats.embModel !== "N/A" && (
              <p className="mt-1 text-[10px] text-surface-400 truncate">
                Model: {stats.embModel}
              </p>
            )}
          </CardContent>
        </Card>

        {/* Indexed Chunks */}
        <Card className="hover:shadow-card-hover transition-shadow">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div className="rounded-lg bg-amber-50 p-2 text-amber-600 dark:bg-amber-950 dark:text-amber-400">
                <HardDrive className="size-5" />
              </div>
              {stats.activeJobs > 0 && (
                <div className="flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-950 dark:text-amber-400">
                  <Loader2 className="size-3 animate-spin" />
                  {stats.activeJobs} active
                </div>
              )}
            </div>
            <p className="mt-4 text-2xl font-bold text-surface-900 dark:text-surface-50">
              {stats.totalChunks.toLocaleString()}
            </p>
            <p className="mt-0.5 text-sm text-surface-500 dark:text-surface-400">
              Indexed Chunks
            </p>
          </CardContent>
        </Card>

        {/* System Health */}
        <Card className="hover:shadow-card-hover transition-shadow">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div className="rounded-lg bg-green-50 p-2 text-green-600 dark:bg-green-950 dark:text-green-400">
                <Activity className="size-5" />
              </div>
              <Badge variant={stats.dbHealthy ? "success" : "destructive"} className="text-[10px]">
                {stats.dbHealthy ? "Healthy" : "Degraded"}
              </Badge>
            </div>
            <p className="mt-4 text-2xl font-bold text-surface-900 dark:text-surface-50">
              {stats.retLatency}
            </p>
            <p className="mt-0.5 text-sm text-surface-500 dark:text-surface-400">
              Retrieval Latency
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Recent Activity / Documents */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Clock className="size-4 text-surface-400" />
              Recent Uploads
            </CardTitle>
          </CardHeader>
          <CardContent>
            {recentDocsLoading ? (
              <div className="flex flex-col gap-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-16 rounded-lg" />
                ))}
              </div>
            ) : documents?.items?.length ? (
              <div className="flex flex-col gap-2">
                {documents.items.map((doc) => (
                  <button
                    key={doc.id}
                    onClick={() => navigate(`/documents/${doc.id}`)}
                    className="flex items-center justify-between rounded-lg border border-surface-100 bg-surface-50/50 p-3 text-left transition-colors hover:border-surface-200 dark:border-surface-700 dark:bg-surface-800/50 dark:hover:border-surface-600"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-surface-900 dark:text-surface-100 truncate">
                        {doc.original_filename}
                      </p>
                      <p className="text-xs text-surface-500 dark:text-surface-400">
                        {doc.mime_type} &middot; {(doc.size_bytes / 1024).toFixed(0)} KB
                      </p>
                    </div>
                    <div className="ml-3 shrink-0">
                      <StatusBadge status={doc.status} />
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center py-8 text-center">
                <Upload className="mb-2 size-8 text-surface-300 dark:text-surface-600" />
                <p className="text-sm text-surface-500">No documents uploaded yet</p>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-3"
                  onClick={() => navigate("/documents")}
                >
                  Upload your first document
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Indexing Queue */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <BarChart3 className="size-4 text-surface-400" />
              Indexing Queue
            </CardTitle>
          </CardHeader>
          <CardContent>
            {indexingJobs && indexingJobs.length > 0 ? (
              <div className="flex flex-col gap-2">
                {indexingJobs.slice(0, 5).map((job) => (
                  <div
                    key={job.job_id}
                    className="flex items-center justify-between rounded-lg border border-surface-100 bg-surface-50/50 p-3 dark:border-surface-700 dark:bg-surface-800/50"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-surface-900 dark:text-surface-100">
                        Job {job.job_id.slice(0, 8)}...
                      </p>
                      <p className="text-xs text-surface-500 dark:text-surface-400">
                        {job.processed_chunks}/{job.total_chunks} chunks
                      </p>
                    </div>
                    <div className="ml-3 shrink-0 flex items-center gap-2">
                      <StatusBadge status={job.status} />
                    </div>
                  </div>
                ))}
              </div>
            ) : stats.totalChunks > 0 ? (
              <div className="flex flex-col items-center py-8 text-center">
                <CheckCircle2 className="mb-2 size-8 text-green-400" />
                <p className="text-sm text-surface-500">All documents indexed</p>
              </div>
            ) : (
              <div className="flex flex-col items-center py-8 text-center">
                <HardDrive className="mb-2 size-8 text-surface-300 dark:text-surface-600" />
                <p className="text-sm text-surface-500">No indexing jobs</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <Sparkles className="size-4 text-surface-400" />
            Quick Actions
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <button
              onClick={() => navigate("/documents")}
              className="flex flex-col items-center gap-2 rounded-xl border border-surface-200 bg-white p-4 transition-all hover:border-brand-300 hover:shadow-sm dark:border-surface-700 dark:bg-surface-800 dark:hover:border-brand-600"
            >
              <Upload className="size-5 text-brand-600 dark:text-brand-400" />
              <span className="text-xs font-medium text-surface-700 dark:text-surface-300">
                Upload Document
              </span>
            </button>
            <button
              onClick={() => navigate("/retrieval")}
              className="flex flex-col items-center gap-2 rounded-xl border border-surface-200 bg-white p-4 transition-all hover:border-brand-300 hover:shadow-sm dark:border-surface-700 dark:bg-surface-800 dark:hover:border-brand-600"
            >
              <Search className="size-5 text-brand-600 dark:text-brand-400" />
              <span className="text-xs font-medium text-surface-700 dark:text-surface-300">
                Search Knowledge
              </span>
            </button>
            <button
              onClick={() => navigate("/chat")}
              className="flex flex-col items-center gap-2 rounded-xl border border-surface-200 bg-white p-4 transition-all hover:border-brand-300 hover:shadow-sm dark:border-surface-700 dark:bg-surface-800 dark:hover:border-brand-600"
            >
              <BookOpen className="size-5 text-brand-600 dark:text-brand-400" />
              <span className="text-xs font-medium text-surface-700 dark:text-surface-300">
                Ask Questions
              </span>
            </button>
            <button
              onClick={() => navigate("/indexing")}
              className="flex flex-col items-center gap-2 rounded-xl border border-surface-200 bg-white p-4 transition-all hover:border-brand-300 hover:shadow-sm dark:border-surface-700 dark:bg-surface-800 dark:hover:border-brand-600"
            >
              <HardDrive className="size-5 text-brand-600 dark:text-brand-400" />
              <span className="text-xs font-medium text-surface-700 dark:text-surface-300">
                Manage Indexing
              </span>
            </button>
          </div>
        </CardContent>
      </Card>

      {/* Error state for failed components */}
      {stats.failedJobs > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-950">
          <AlertCircle className="size-5 text-red-500 shrink-0" />
          <div>
            <p className="text-sm font-medium text-red-800 dark:text-red-300">
              {stats.failedJobs} indexing job(s) failed
            </p>
            <p className="text-xs text-red-600 dark:text-red-400">
              Check the Indexing page for details and retry options
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="ml-auto shrink-0"
            onClick={() => navigate("/indexing")}
          >
            View Jobs
          </Button>
        </div>
      )}
    </div>
  );
}
