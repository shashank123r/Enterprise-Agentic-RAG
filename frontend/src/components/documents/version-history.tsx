import { useState } from "react";
import { Clock, RotateCcw, CheckCircle2, XCircle, FileWarning } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import type { DocumentVersion } from "../../services/document.service";

interface VersionHistoryProps {
  versions: DocumentVersion[];
  currentVersion: number;
  onRestore: (version: number) => void;
  onDelete?: (version: number) => void;
  loading?: boolean;
}

export function VersionHistory({
  versions,
  currentVersion,
  onRestore,
  onDelete,
  loading,
}: VersionHistoryProps) {
  const [restoringVersion, setRestoringVersion] = useState<number | null>(null);

  const sortedVersions = [...versions].sort((a, b) => b.version - a.version);

  const handleRestore = async (version: number) => {
    setRestoringVersion(version);
    try {
      await onRestore(version);
    } finally {
      setRestoringVersion(null);
    }
  };

  return (
    <div className="space-y-3">
      {sortedVersions.length === 0 && !loading && (
        <div className="flex flex-col items-center gap-2 py-8 text-surface-400">
          <Clock className="size-8" />
          <p className="text-sm">No version history available</p>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-8">
          <div className="size-6 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
        </div>
      )}

      <AnimatePresence>
        {sortedVersions.map((version) => {
          const isCurrent = version.version === currentVersion;
          const isRestoring = restoringVersion === version.version;

          return (
            <motion.div
              key={version.version}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={cn(
                "relative flex items-start gap-3 rounded-lg border p-3 transition-all",
                isCurrent
                  ? "border-brand-500 bg-brand-50 dark:border-brand-400 dark:bg-brand-950"
                  : "border-surface-200 bg-white dark:border-surface-700 dark:bg-surface-800",
              )}
            >
              {/* Version timeline dot */}
              <div
                className={cn(
                  "mt-1 flex size-5 shrink-0 items-center justify-center rounded-full border",
                  isCurrent
                    ? "border-brand-500 bg-brand-500 text-white"
                    : "border-surface-300 bg-white text-surface-400 dark:border-surface-600 dark:bg-surface-800",
                )}
              >
                <span className="text-[10px] font-bold">{version.version}</span>
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-surface-900 dark:text-surface-100">
                      Version {version.version}
                    </span>
                    {isCurrent && (
                      <Badge variant="success" className="text-[10px]">
                        Current
                      </Badge>
                    )}
                    {version.indexed && (
                      <Badge variant="default" className="text-[10px]">
                        Indexed
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    {version.status === "completed" && (
                      <CheckCircle2 className="size-4 text-green-500" />
                    )}
                    {version.status === "failed" && (
                      <XCircle className="size-4 text-red-500" />
                    )}
                    {version.status === "processing" && (
                      <FileWarning className="size-4 text-amber-500" />
                    )}
                  </div>
                </div>

                <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-surface-500">
                  <span>Created: {new Date(version.created_at).toLocaleDateString()}</span>
                  <span>Size: {(version.file_size / 1024).toFixed(0)} KB</span>
                  {version.indexed_at && (
                    <span>
                      Indexed: {new Date(version.indexed_at).toLocaleDateString()}
                    </span>
                  )}
                </div>

                {version.changes && (
                  <p className="mt-1 text-xs text-surface-500">{version.changes}</p>
                )}

                {!isCurrent && version.status === "completed" && (
                  <div className="mt-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleRestore(version.version)}
                      disabled={isRestoring}
                    >
                      {isRestoring ? (
                        <>
                          <div className="mr-1.5 size-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                          Restoring...
                        </>
                      ) : (
                        <>
                          <RotateCcw className="mr-1.5 size-3" />
                          Restore
                        </>
                      )}
                    </Button>
                  </div>
                )}
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
