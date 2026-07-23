import { useState } from "react";
import {
  Database,
  RefreshCw,
  Trash2,
  XCircle,
  Play,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Progress } from "../ui/progress";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";
import type { IndexingJob } from "../../types";

interface IndexManagementProps {
  indexingJobs: IndexingJob[];
  documentId: string;
  documentStatus: string;
  onStartIndexing: () => void;
  onCancelIndexing: () => void;
  onRetryIndexing: () => void;
  onDeleteIndex: () => void;
  loading?: boolean;
}

const statusConfig: Record<string, { label: string; variant: "default" | "success" | "warning" | "destructive" }> = {
  queued: { label: "Queued", variant: "default" },
  embedding: { label: "Embedding", variant: "warning" },
  writing: { label: "Writing to Milvus", variant: "warning" },
  completed: { label: "Completed", variant: "success" },
  failed: { label: "Failed", variant: "destructive" },
  cancelled: { label: "Cancelled", variant: "default" },
};

export function IndexManagement({
  indexingJobs,
  documentId,
  documentStatus,
  onStartIndexing,
  onCancelIndexing,
  onRetryIndexing,
  onDeleteIndex,
  loading,
}: IndexManagementProps) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const mostRecentJob = indexingJobs[0];
  const hasActiveJob = mostRecentJob && ["queued", "embedding", "writing"].includes(mostRecentJob.status);
  const hasFailedJob = mostRecentJob?.status === "failed";
  const hasCompletedIndex = mostRecentJob?.status === "completed" || documentStatus === "indexed";

  return (
    <div className="space-y-4">
      {/* Current index status */}
      <div className="rounded-lg border border-surface-200 bg-white p-4 dark:border-surface-700 dark:bg-surface-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Database className="size-5 text-surface-400" />
            <div>
              <p className="text-sm font-medium text-surface-900 dark:text-surface-100">
                Vector Index
              </p>
              <p className="text-xs text-surface-500">
                {hasCompletedIndex
                  ? "Index is built and ready"
                  : hasActiveJob
                    ? "Indexing in progress..."
                    : hasFailedJob
                      ? "Indexing failed"
                      : "Not yet indexed"}
              </p>
            </div>
          </div>
          {mostRecentJob && (
            <Badge variant={statusConfig[mostRecentJob.status]?.variant || "default"}>
              {statusConfig[mostRecentJob.status]?.label || mostRecentJob.status}
            </Badge>
          )}
        </div>

        {/* Active job progress */}
        {hasActiveJob && mostRecentJob && (
          <div className="mt-3">
            <div className="flex items-center justify-between text-xs text-surface-500">
              <span>
                {mostRecentJob.chunks_embedded} / {mostRecentJob.chunks_total} chunks
              </span>
              <span>{Math.round(mostRecentJob.progress)}%</span>
            </div>
            <Progress value={mostRecentJob.progress} className="mt-1 h-1.5" />
          </div>
        )}

        {/* Actions */}
        <div className="mt-3 flex items-center gap-2">
          {!hasActiveJob && !hasCompletedIndex && (
            <Button size="sm" onClick={onStartIndexing} disabled={loading}>
              <Play className="mr-1.5 size-3.5" />
              Start Indexing
            </Button>
          )}
          {hasActiveJob && (
            <Button
              variant="outline"
              size="sm"
              onClick={onCancelIndexing}
              disabled={loading}
            >
              <XCircle className="mr-1.5 size-3.5" />
              Cancel
            </Button>
          )}
          {hasFailedJob && (
            <Button
              variant="outline"
              size="sm"
              onClick={onRetryIndexing}
              disabled={loading}
            >
              <RefreshCw className="mr-1.5 size-3.5" />
              Retry
            </Button>
          )}
          {hasCompletedIndex && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={onStartIndexing}
                disabled={loading}
              >
                <RefreshCw className="mr-1.5 size-3.5" />
                Re-index
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowDeleteConfirm(true)}
                className="text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
              >
                <Trash2 className="mr-1.5 size-3.5" />
                Delete Index
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Job history */}
      {indexingJobs.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-surface-500 uppercase tracking-wider">
            Indexing History
          </h4>
          <div className="space-y-1">
            {indexingJobs.slice(0, 5).map((job) => (
              <div
                key={job.id}
                className="flex items-center justify-between rounded-lg border border-surface-100 bg-surface-50 px-3 py-2 text-xs dark:border-surface-800 dark:bg-surface-800/50"
              >
                <div className="flex items-center gap-2">
                  <Badge variant={statusConfig[job.status]?.variant || "default"} className="text-[10px]">
                    {statusConfig[job.status]?.label || job.status}
                  </Badge>
                  <span className="text-surface-500">
                    {job.chunks_total > 0
                      ? `${Math.round(job.progress)}% (${job.chunks_embedded}/${job.chunks_total})`
                      : "Waiting..."}
                  </span>
                </div>
                <span className="text-surface-400">
                  {new Date(job.created_at).toLocaleDateString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Delete confirmation dialog */}
      <Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="size-5 text-red-500" />
              Delete Vector Index
            </DialogTitle>
            <DialogDescription>
              This will permanently remove the vector index for this document. The document will
              need to be re-indexed before it can be found in searches. The original document and
              its chunks will not be affected.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteConfirm(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                onDeleteIndex();
                setShowDeleteConfirm(false);
              }}
            >
              <Trash2 className="mr-2 size-4" />
              Delete Index
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
