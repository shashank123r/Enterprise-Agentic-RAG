import { motion } from "framer-motion";
import {
  Upload,
  FileSearch,
  ScanText,
  Sparkles,
  Scissors,
  Brain,
  Database,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
} from "lucide-react";
import { cn } from "../../lib/utils";
import type { ProcessingStage } from "../../services/document.service";

const stageIcons: Record<string, React.ElementType> = {
  upload: Upload,
  validating: FileSearch,
  extracting: FileSearch,
  ocr: ScanText,
  cleaning: Sparkles,
  chunking: Scissors,
  embedding: Brain,
  indexing: Database,
};

const stageLabels: Record<string, string> = {
  upload: "Upload",
  validating: "Validating",
  extracting: "Extracting",
  ocr: "OCR",
  cleaning: "Cleaning",
  chunking: "Chunking",
  embedding: "Embedding",
  indexing: "Indexing",
};

interface ProcessingPipelineProps {
  stages: ProcessingStage[];
  overallStatus: string;
  overallProgress: number;
}

export function ProcessingPipeline({ stages, overallStatus, overallProgress }: ProcessingPipelineProps) {
  return (
    <div className="rounded-xl border border-surface-200 bg-white p-5 dark:border-surface-700 dark:bg-surface-800">
      {/* Overall progress */}
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-surface-900 dark:text-surface-100">
            Processing Pipeline
          </h3>
          <p className="text-xs text-surface-500">
            {overallStatus === "processing" && "Processing your document..."}
            {overallStatus === "completed" && "All stages complete"}
            {overallStatus === "failed" && "Processing failed"}
            {overallStatus === "pending" && "Waiting to start..."}
            {overallStatus === "cancelled" && "Processing cancelled"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-surface-500">
            {Math.round(overallProgress)}%
          </span>
          {overallStatus === "processing" && (
            <Loader2 className="size-4 animate-spin text-brand-500" />
          )}
          {overallStatus === "completed" && (
            <CheckCircle2 className="size-4 text-green-500" />
          )}
          {overallStatus === "failed" && (
            <XCircle className="size-4 text-red-500" />
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-5 h-2 overflow-hidden rounded-full bg-surface-100 dark:bg-surface-700">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-brand-500 to-brand-600"
          initial={{ width: 0 }}
          animate={{ width: `${Math.round(overallProgress)}%` }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        />
      </div>

      {/* Stage list */}
      <div className="space-y-0">
        {stages.map((stage, index) => {
          const Icon = stageIcons[stage.name] || FileSearch;
          const isLast = index === stages.length - 1;

          return (
            <div key={stage.name} className="relative flex gap-3">
              {/* Vertical connector line */}
              {!isLast && (
                <div
                  className={cn(
                    "absolute left-[13.5px] top-8 w-0.5 h-8",
                    stage.status === "completed"
                      ? "bg-green-500"
                      : "bg-surface-200 dark:bg-surface-600",
                  )}
                />
              )}

              {/* Stage icon */}
              <div
                className={cn(
                  "relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full border transition-all duration-300",
                  stage.status === "completed" &&
                    "border-green-500 bg-green-50 text-green-600 dark:bg-green-950 dark:text-green-400",
                  stage.status === "processing" &&
                    "border-brand-500 bg-brand-50 text-brand-600 dark:bg-brand-950 dark:text-brand-400",
                  stage.status === "failed" &&
                    "border-red-500 bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400",
                  stage.status === "skipped" &&
                    "border-surface-300 bg-surface-100 text-surface-400 dark:border-surface-600 dark:bg-surface-800 dark:text-surface-500",
                  (stage.status === "pending" || stage.status === "skipped") &&
                    "border-surface-300 bg-white text-surface-300 dark:border-surface-600 dark:bg-surface-800 dark:text-surface-600",
                )}
              >
                {stage.status === "processing" ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : stage.status === "completed" ? (
                  <CheckCircle2 className="size-3.5" />
                ) : stage.status === "failed" ? (
                  <XCircle className="size-3.5" />
                ) : (
                  <Icon className="size-3.5" />
                )}
              </div>

              {/* Stage content */}
              <div className="flex-1 pb-6">
                <div className="flex items-center justify-between">
                  <span
                    className={cn(
                      "text-sm font-medium",
                      stage.status === "completed" && "text-surface-500 dark:text-surface-400",
                      stage.status === "processing" && "text-surface-900 dark:text-surface-100",
                      stage.status === "failed" && "text-red-600 dark:text-red-400",
                      (stage.status === "pending" || stage.status === "skipped") &&
                        "text-surface-400 dark:text-surface-500",
                    )}
                  >
                    {stageLabels[stage.name] || stage.name}
                  </span>
                  <div className="flex items-center gap-2">
                    {stage.status === "processing" && stage.progress > 0 && (
                      <span className="text-xs text-brand-600 dark:text-brand-400">
                        {stage.progress}%
                      </span>
                    )}
                    {stage.duration_ms != null && (
                      <span className="text-xs text-surface-400">
                        {(stage.duration_ms / 1000).toFixed(1)}s
                      </span>
                    )}
                  </div>
                </div>

                {stage.status === "failed" && stage.error && (
                  <p className="mt-0.5 text-xs text-red-500">{stage.error}</p>
                )}

                {/* Stage progress bar */}
                {stage.status === "processing" && stage.progress > 0 && (
                  <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-surface-100 dark:bg-surface-700">
                    <motion.div
                      className="h-full rounded-full bg-brand-500"
                      initial={{ width: 0 }}
                      animate={{ width: `${stage.progress}%` }}
                      transition={{ duration: 0.5 }}
                    />
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
