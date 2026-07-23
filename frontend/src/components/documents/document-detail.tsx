import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  FileText,
  Info,
  ListTree,
  Clock,
  Database,
  History,
  Trash2,
  Download,
  Loader2,
  AlertCircle,
  FileCode,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "../../lib/utils";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Progress } from "../ui/progress";
import { Skeleton } from "../ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";
import { ProcessingPipeline } from "./processing-pipeline";
import { ChunkViewer } from "./chunk-viewer";
import { VersionHistory } from "./version-history";
import { IndexManagement } from "./index-management";
import {
  useDocument,
  useDocumentMetadata,
  useDocumentChunks,
  useDocumentText,
  useProcessingStatus,
  useIndexingJobs,
  useDocumentVersions,
  useDeleteDocument,
  useCancelProcessing,
  useRetryProcessing,
  useStartIndexing,
  useCancelIndexing,
  useRetryIndexing,
  useDeleteIndex,
  useRestoreVersion,
} from "../../hooks/useDocuments";

type TabId = "overview" | "metadata" | "chunks" | "versions" | "processing" | "indexing";

const tabs: { id: TabId; label: string; icon: React.ElementType }[] = [
  { id: "overview", label: "Overview", icon: FileText },
  { id: "metadata", label: "Metadata", icon: Info },
  { id: "text", label: "Extracted Text", icon: FileCode },
  { id: "chunks", label: "Chunks", icon: ListTree },
  { id: "processing", label: "Processing", icon: Clock },
  { id: "indexing", label: "Index", icon: Database },
  { id: "versions", label: "Versions", icon: History },
];

interface DocumentDetailProps {
  documentId: string;
}

export function DocumentDetail({ documentId }: DocumentDetailProps) {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [chunkPage, setChunkPage] = useState(1);
  const [chunkSearch, setChunkSearch] = useState("");
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  // Queries
  const { data: document, isLoading: docLoading, error: docError } = useDocument(documentId);
  const { data: metadata, isLoading: metaLoading } = useDocumentMetadata(documentId);
  const { data: chunksData, isLoading: chunksLoading } = useDocumentChunks(documentId, {
    page: chunkPage,
    page_size: 20,
    search: chunkSearch || undefined,
  });
  const { data: extractedText, isLoading: textLoading } = useDocumentText(documentId);
  const { data: processing, isLoading: procLoading } = useProcessingStatus(documentId);
  const { data: indexingJobs, isLoading: indexingLoading } = useIndexingJobs(documentId);
  const { data: versions, isLoading: versionsLoading } = useDocumentVersions(documentId);

  // Mutations
  const deleteMutation = useDeleteDocument();
  const cancelProcMutation = useCancelProcessing();
  const retryProcMutation = useRetryProcessing();
  const startIdxMutation = useStartIndexing();
  const cancelIdxMutation = useCancelIndexing();
  const retryIdxMutation = useRetryIndexing();
  const deleteIdxMutation = useDeleteIndex();
  const restoreVersionMutation = useRestoreVersion();

  // Auto-poll processing while active
  const isProcessing = processing?.status === "processing";

  if (docError) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <AlertCircle className="size-12 text-red-500" />
        <h2 className="text-lg font-semibold text-surface-900 dark:text-surface-100">
          Document not found
        </h2>
        <p className="text-sm text-surface-500">The document could not be loaded.</p>
        <Button variant="outline" onClick={() => navigate("/documents")}>
          Back to Documents
        </Button>
      </div>
    );
  }

  if (docLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate("/documents")}
            className="mt-1"
          >
            <ArrowLeft className="size-4" />
          </Button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-bold text-surface-900 dark:text-surface-50">
                {document?.title || document?.filename}
              </h1>
              <Badge
                variant={
                  document?.status === "completed"
                    ? "success"
                    : document?.status === "processing"
                      ? "warning"
                      : document?.status === "failed"
                        ? "destructive"
                        : "default"
                }
              >
                {document?.status}
              </Badge>
            </div>
            <p className="mt-1 text-sm text-surface-500">
              {document?.file_type?.toUpperCase()} &middot;{" "}
              {document?.file_size ? `${(document.file_size / 1024 / 1024).toFixed(1)} MB` : ""}
              {document?.pages ? ` \u00b7 ${document.pages} pages` : ""}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm">
            <Download className="mr-1.5 size-3.5" />
            Download
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowDeleteDialog(true)}
            className="text-red-600 hover:text-red-700 dark:text-red-400"
          >
            <Trash2 className="mr-1.5 size-3.5" />
            Delete
          </Button>
        </div>
      </div>

      {/* Processing banner */}
      {isProcessing && processing && (
        <div className="rounded-lg border border-brand-200 bg-brand-50 p-4 dark:border-brand-900 dark:bg-brand-950">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Loader2 className="size-5 animate-spin text-brand-600" />
              <div>
                <p className="text-sm font-medium text-brand-800 dark:text-brand-200">
                  Processing document...
                </p>
                <p className="text-xs text-brand-600 dark:text-brand-400">
                  {processing.stages?.find((s) => s.status === "processing")?.name || "Processing"}{" "}
                  stage &middot; {Math.round(processing.progress)}%
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => cancelProcMutation.mutate(documentId)}
            >
              Cancel
            </Button>
          </div>
          <Progress value={processing.progress} className="mt-3" />
        </div>
      )}

      {/* Failed banner */}
      {document?.status === "failed" && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-900 dark:bg-red-950">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <AlertCircle className="size-5 text-red-600" />
              <div>
                <p className="text-sm font-medium text-red-800 dark:text-red-200">
                  Processing failed
                </p>
                <p className="text-xs text-red-600 dark:text-red-400">
                  {processing?.error || "An error occurred during processing"}
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => retryProcMutation.mutate(documentId)}
            >
              Retry
            </Button>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-surface-200 dark:border-surface-700">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-all duration-200 border-b-2 -mb-px",
              activeTab === tab.id
                ? "border-brand-600 text-brand-700 dark:border-brand-400 dark:text-brand-300"
                : "border-transparent text-surface-500 hover:text-surface-700 dark:hover:text-surface-300",
            )}
          >
            <tab.icon className="size-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.15 }}
        >
          {/* Overview tab */}
          {activeTab === "overview" && (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              <div className="lg:col-span-2 space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle>Document Info</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <dl className="grid grid-cols-2 gap-4 text-sm">
                      {[
                        ["Filename", document?.filename],
                        ["File Type", document?.file_type?.toUpperCase()],
                        ["File Size", document?.file_size ? `${(document.file_size / 1024 / 1024).toFixed(2)} MB` : "-"],
                        ["Pages", String(document?.pages ?? "-")],
                        ["Language", document?.language || "Detecting..."],
                        ["Checksum", document?.checksum?.slice(0, 16) + "..."],
                        ["Version", String(document?.version ?? 1)],
                        ["Created", document?.created_at ? new Date(document.created_at).toLocaleString() : "-"],
                        ["Updated", document?.updated_at ? new Date(document.updated_at).toLocaleString() : "-"],
                      ].map(([label, value]) => (
                        <div key={label} className="flex flex-col gap-0.5">
                          <dt className="text-xs text-surface-500">{label}</dt>
                          <dd className="font-medium text-surface-900 dark:text-surface-100 truncate">
                            {value || "-"}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </CardContent>
                </Card>

                {chunksData && (
                  <Card>
                    <CardHeader>
                      <CardTitle>Chunks</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex items-center gap-4 text-sm">
                        <div>
                          <span className="text-2xl font-bold text-surface-900 dark:text-surface-50">
                            {chunksData.total}
                          </span>
                          <p className="text-xs text-surface-500">Total chunks</p>
                        </div>
                        <div className="h-10 w-px bg-surface-200 dark:bg-surface-700" />
                        <div>
                          <span className="text-2xl font-bold text-surface-900 dark:text-surface-50">
                            {metadata?.page_count || document?.pages || "-"}
                          </span>
                          <p className="text-xs text-surface-500">Pages</p>
                        </div>
                        <div className="h-10 w-px bg-surface-200 dark:bg-surface-700" />
                        <div>
                          <span className="text-2xl font-bold text-surface-900 dark:text-surface-50">
                            {indexingJobs?.[0]?.chunks_embedded || 0}
                          </span>
                          <p className="text-xs text-surface-500">Indexed</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </div>

              <div className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle>Processing</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {procLoading ? (
                      <Skeleton className="h-20" />
                    ) : processing ? (
                      <div className="space-y-2">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-surface-500">Status</span>
                          <Badge
                            variant={
                              processing.status === "completed"
                                ? "success"
                                : processing.status === "failed"
                                  ? "destructive"
                                  : processing.status === "processing"
                                    ? "warning"
                                    : "default"
                            }
                          >
                            {processing.status}
                          </Badge>
                        </div>
                        <Progress value={processing.progress} className="h-1.5" />
                        <div className="flex items-center justify-between text-xs text-surface-500">
                          <span>{Math.round(processing.progress)}% complete</span>
                          {processing.stages && (
                            <span>
                              {processing.stages.filter((s) => s.status === "completed").length}/
                              {processing.stages.length} stages
                            </span>
                          )}
                        </div>
                      </div>
                    ) : (
                      <p className="text-sm text-surface-400">No processing data</p>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Index</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {indexingLoading ? (
                      <Skeleton className="h-16" />
                    ) : (
                      <div className="text-sm">
                        <div className="flex items-center justify-between">
                          <span className="text-surface-500">Status</span>
                          <Badge
                            variant={
                              indexingJobs?.[0]?.status === "completed"
                                ? "success"
                                : indexingJobs?.[0]?.status === "failed"
                                  ? "destructive"
                                  : indexingJobs?.[0]?.status
                                    ? "warning"
                                    : "default"
                            }
                          >
                            {indexingJobs?.[0]?.status || "Not Started"}
                          </Badge>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            </div>
          )}

          {/* Metadata tab */}
          {activeTab === "metadata" && (
            <Card>
              <CardHeader>
                <CardTitle>Document Metadata</CardTitle>
              </CardHeader>
              <CardContent>
                {metaLoading ? (
                  <div className="space-y-3">
                    <Skeleton className="h-5 w-full" />
                    <Skeleton className="h-5 w-3/4" />
                    <Skeleton className="h-5 w-1/2" />
                  </div>
                ) : metadata ? (
                  <div className="space-y-6">
                    <div>
                      <h4 className="mb-2 text-xs font-semibold text-surface-500 uppercase tracking-wider">
                        Basic Info
                      </h4>
                      <dl className="grid grid-cols-2 gap-3 text-sm">
                        {[
                          ["Title", metadata.title],
                          ["Author", metadata.author],
                          ["Created", metadata.creation_date ? new Date(metadata.creation_date).toLocaleDateString() : "-"],
                          ["Modified", metadata.modified_date ? new Date(metadata.modified_date).toLocaleDateString() : "-"],
                          ["Language", metadata.language],
                          ["Pages", String(metadata.page_count)],
                        ].map(([label, value]) => (
                          <div key={label}>
                            <dt className="text-xs text-surface-500">{label}</dt>
                            <dd className="font-medium text-surface-900 dark:text-surface-100">
                              {value || "-"}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </div>

                    {metadata.section_hierarchy?.length > 0 && (
                      <div>
                        <h4 className="mb-2 text-xs font-semibold text-surface-500 uppercase tracking-wider">
                          Sections
                        </h4>
                        <div className="flex flex-wrap gap-1">
                          {metadata.section_hierarchy.map((section, i) => (
                            <Badge key={i} variant="outline" className="text-xs">
                              {section}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}

                    {metadata.keywords?.length > 0 && (
                      <div>
                        <h4 className="mb-2 text-xs font-semibold text-surface-500 uppercase tracking-wider">
                          Keywords
                        </h4>
                        <div className="flex flex-wrap gap-1">
                          {metadata.keywords.map((kw, i) => (
                            <Badge key={i} variant="secondary" className="text-xs">
                              {kw}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}

                    {metadata.statistics && Object.keys(metadata.statistics).length > 0 && (
                      <div>
                        <h4 className="mb-2 text-xs font-semibold text-surface-500 uppercase tracking-wider">
                          Statistics
                        </h4>
                        <dl className="grid grid-cols-2 gap-2 text-sm">
                          {Object.entries(metadata.statistics).map(([key, value]) => (
                            <div key={key}>
                              <dt className="text-xs text-surface-500 capitalize">
                                {key.replace(/_/g, " ")}
                              </dt>
                              <dd className="font-medium text-surface-900 dark:text-surface-100">
                                {String(value)}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      </div>
                    )}

                    {metadata.custom && Object.keys(metadata.custom).length > 0 && (
                      <div>
                        <h4 className="mb-2 text-xs font-semibold text-surface-500 uppercase tracking-wider">
                          Custom Metadata
                        </h4>
                        <dl className="grid grid-cols-2 gap-2 text-sm">
                          {Object.entries(metadata.custom).map(([key, value]) => (
                            <div key={key}>
                              <dt className="text-xs text-surface-500">{key}</dt>
                              <dd className="font-medium text-surface-900 dark:text-surface-100">
                                {value}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-surface-400">No metadata available</p>
                )}
              </CardContent>
            </Card>
          )}

          {/* Extracted Text tab */}
          {activeTab === "text" && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>Extracted Text</CardTitle>
                {extractedText && (
                  <span className="text-xs text-surface-400">
                    {extractedText.length.toLocaleString()} characters
                  </span>
                )}
              </CardHeader>
              <CardContent>
                {textLoading ? (
                  <div className="space-y-3">
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="h-4 w-5/6" />
                    <Skeleton className="h-4 w-4/6" />
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="h-4 w-3/4" />
                  </div>
                ) : extractedText ? (
                  <pre className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap rounded-lg border border-surface-200 bg-surface-50 p-4 text-sm leading-relaxed text-surface-800 dark:border-surface-700 dark:bg-surface-900 dark:text-surface-200">
                    {extractedText}
                  </pre>
                ) : (
                  <p className="text-sm text-surface-400">No extracted text available</p>
                )}
              </CardContent>
            </Card>
          )}

          {/* Chunks tab */}
          {activeTab === "chunks" && (
            <Card>
              <CardHeader>
                <CardTitle>Document Chunks</CardTitle>
              </CardHeader>
              <CardContent>
                <ChunkViewer
                  chunks={chunksData?.items || []}
                  total={chunksData?.total || 0}
                  page={chunkPage}
                  pageSize={20}
                  onPageChange={setChunkPage}
                  onSearch={setChunkSearch}
                  loading={chunksLoading}
                />
              </CardContent>
            </Card>
          )}

          {/* Processing tab */}
          {activeTab === "processing" && (
            <div className="max-w-2xl">
              {procLoading ? (
                <Skeleton className="h-64" />
              ) : processing ? (
                <ProcessingPipeline
                  stages={processing.stages}
                  overallStatus={processing.status}
                  overallProgress={processing.progress}
                />
              ) : (
                <p className="text-sm text-surface-400">No processing data available</p>
              )}
            </div>
          )}

          {/* Indexing tab */}
          {activeTab === "indexing" && (
            <div className="max-w-lg">
              <IndexManagement
                indexingJobs={indexingJobs || []}
                documentId={documentId}
                documentStatus={document?.status || "pending"}
                onStartIndexing={() => startIdxMutation.mutate(documentId)}
                onCancelIndexing={() => cancelIdxMutation.mutate(documentId)}
                onRetryIndexing={() => retryIdxMutation.mutate(documentId)}
                onDeleteIndex={() => deleteIdxMutation.mutate(documentId)}
                loading={indexingLoading}
              />
            </div>
          )}

          {/* Versions tab */}
          {activeTab === "versions" && (
            <div className="max-w-xl">
              <Card>
                <CardHeader>
                  <CardTitle>Version History</CardTitle>
                </CardHeader>
                <CardContent>
                  <VersionHistory
                    versions={versions || []}
                    currentVersion={document?.version || 1}
                    onRestore={(version) =>
                      restoreVersionMutation.mutate({ id: documentId, version })
                    }
                    loading={versionsLoading}
                  />
                </CardContent>
              </Card>
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      {/* Delete confirmation */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Document</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this document? This will remove the document, its
              chunks, and its vector index. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteDialog(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                deleteMutation.mutate(documentId);
                setShowDeleteDialog(false);
                navigate("/documents");
              }}
            >
              <Trash2 className="mr-2 size-4" />
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
