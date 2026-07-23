import { useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  HardDrive,
  Play,
  RotateCcw,
  XCircle,
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  RefreshCw,
  StopCircle,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Progress } from "../components/ui/progress";
import { Skeleton } from "../components/ui/skeleton";
import { useLayoutStore, useNotificationsStore } from "../store";
import { indexingService } from "../services/indexing.service";

function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, { variant: "success" | "warning" | "destructive" | "outline" | "default"; label: string; icon: React.ElementType }> = {
    completed: { variant: "success", label: "Completed", icon: CheckCircle2 },
    processing: { variant: "warning", label: "Processing", icon: Loader2 },
    embedding: { variant: "warning", label: "Embedding", icon: Loader2 },
    writing: { variant: "warning", label: "Writing", icon: Loader2 },
    queued: { variant: "outline", label: "Queued", icon: Clock },
    failed: { variant: "destructive", label: "Failed", icon: AlertCircle },
    cancelled: { variant: "outline", label: "Cancelled", icon: XCircle },
    retrying: { variant: "warning", label: "Retrying", icon: RefreshCw },
  };
  const v = variants[status] ?? { variant: "outline" as const, label: status, icon: Clock };
  const Icon = v.icon;
  return (
    <Badge variant={v.variant} className="text-[10px] flex items-center gap-1">
      {status === "processing" || status === "embedding" || status === "writing" ? (
        <Loader2 className="size-3 animate-spin" />
      ) : (
        <Icon className="size-3" />
      )}
      {v.label}
    </Badge>
  );
}

export function IndexingPage() {
  const navigate = useNavigate();
  const setPageTitle = useLayoutStore((s) => s.setPageTitle);
  const addNotification = useNotificationsStore((s) => s.addNotification);
  const queryClient = useQueryClient();

  useEffect(() => {
    setPageTitle("Indexing Jobs");
  }, [setPageTitle]);

  const { data: jobs, isLoading, error, refetch } = useQuery({
    queryKey: ["indexing", "jobs", "all"],
    queryFn: () => indexingService.listJobs(undefined, 50),
    refetchInterval: 5_000,
  });

  const { data: stats } = useQuery({
    queryKey: ["indexing", "stats"],
    queryFn: () => indexingService.getStats(),
    refetchInterval: 10_000,
  });

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => indexingService.cancelJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["indexing"] });
      addNotification({ type: "success", title: "Cancelled", message: "Indexing job cancelled" });
    },
    onError: (e: Error) => addNotification({ type: "error", title: "Cancel failed", message: e.message }),
  });

  const retryMutation = useMutation({
    mutationFn: (jobId: string) => indexingService.retryJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["indexing"] });
      addNotification({ type: "success", title: "Retrying", message: "Job queued for retry" });
    },
    onError: (e: Error) => addNotification({ type: "error", title: "Retry failed", message: e.message }),
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <div>
          <Skeleton className="h-8 w-48" />
          <Skeleton className="mt-2 h-4 w-64" />
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  const activeJobs = jobs?.filter(j => ["queued", "processing", "embedding", "writing", "retrying"].includes(j.status)) ?? [];
  const completedJobs = jobs?.filter(j => j.status === "completed") ?? [];
  const failedJobs = jobs?.filter(j => j.status === "failed") ?? [];

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-surface-900 dark:text-surface-50">Indexing Jobs</h1>
          <p className="mt-1 text-sm text-surface-500">Monitor and manage embedding jobs</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="size-3.5 mr-1.5" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-brand-50 p-2 text-brand-600 dark:bg-brand-950 dark:text-brand-400">
              <HardDrive className="size-4" />
            </div>
            <div>
              <p className="text-lg font-bold text-surface-900 dark:text-surface-50">{jobs?.length ?? 0}</p>
              <p className="text-xs text-surface-500">Total Jobs</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-amber-50 p-2 text-amber-600 dark:bg-amber-950 dark:text-amber-400">
              <Loader2 className="size-4 animate-spin" />
            </div>
            <div>
              <p className="text-lg font-bold text-surface-900 dark:text-surface-50">{activeJobs.length}</p>
              <p className="text-xs text-surface-500">Active</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-green-50 p-2 text-green-600 dark:bg-green-950 dark:text-green-400">
              <CheckCircle2 className="size-4" />
            </div>
            <div>
              <p className="text-lg font-bold text-surface-900 dark:text-surface-50">{completedJobs.length}</p>
              <p className="text-xs text-surface-500">Completed</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-red-50 p-2 text-red-600 dark:bg-red-950 dark:text-red-400">
              <AlertCircle className="size-4" />
            </div>
            <div>
              <p className="text-lg font-bold text-surface-900 dark:text-surface-50">{failedJobs.length}</p>
              <p className="text-xs text-surface-500">Failed</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Job list */}
      {error ? (
        <Card>
          <CardContent className="flex flex-col items-center py-12 text-center">
            <AlertCircle className="mb-3 size-10 text-red-400" />
            <h3 className="text-sm font-medium">Failed to load indexing jobs</h3>
            <p className="mt-1 text-xs text-surface-500">{(error as Error).message}</p>
            <Button variant="outline" size="sm" className="mt-4" onClick={() => refetch()}>
              <RefreshCw className="mr-1.5 size-3.5" />
              Retry
            </Button>
          </CardContent>
        </Card>
      ) : jobs && jobs.length > 0 ? (
        <Card>
          <CardContent className="p-0">
            <div className="divide-y divide-surface-100 dark:divide-surface-700">
              {jobs.map((job) => (
                <div key={job.job_id} className="px-5 py-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3 min-w-0">
                      <HardDrive className="size-4 text-surface-400 shrink-0" />
                      <div className="min-w-0">
                        <span className="text-sm font-medium text-surface-900 dark:text-surface-100">
                          Job {job.job_id.slice(0, 8)}...
                        </span>
                        <span className="ml-2 text-xs text-surface-400">
                          {job.document_id ? `Doc: ${job.document_id.slice(0, 8)}...` : ""}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 ml-3">
                      <StatusBadge status={job.status} />
                      {job.status === "queued" && (
                        <button
                          onClick={() => cancelMutation.mutate(job.job_id)}
                          className="p-1 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300"
                          title="Cancel"
                        >
                          <StopCircle className="size-4" />
                        </button>
                      )}
                      {job.status === "failed" && (
                        <button
                          onClick={() => retryMutation.mutate(job.job_id)}
                          className="p-1 text-surface-400 hover:text-surface-600 dark:hover:text-surface-300"
                          title="Retry"
                        >
                          <RotateCcw className="size-4" />
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <Progress
                      value={job.processed_chunks > 0 ? (job.processed_chunks / (job.total_chunks || 1)) * 100 : 0}
                      className="flex-1 h-1.5"
                    />
                    <span className="text-xs text-surface-400 w-32 text-right shrink-0">
                      {job.processed_chunks}/{job.total_chunks} chunks
                      {job.failed_chunks > 0 && <span className="text-red-400"> ({job.failed_chunks} failed)</span>}
                    </span>
                  </div>
                  {job.error_message && (
                    <p className="mt-1.5 text-xs text-red-500 dark:text-red-400">{job.error_message}</p>
                  )}
                  {job.cache_hits > 0 && (
                    <p className="mt-0.5 text-[10px] text-surface-400">{job.cache_hits} cache hits</p>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center py-16 text-center">
            <HardDrive className="mb-3 size-10 text-surface-300 dark:text-surface-600" />
            <h3 className="text-sm font-medium text-surface-900 dark:text-surface-100">No Indexing Jobs</h3>
            <p className="mt-1 text-xs text-surface-500 max-w-xs">
              Upload and process a document to start indexing. Jobs will appear here once created.
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
