import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  FileText,
  Search,
  Filter,
  ArrowUpDown,
  MoreHorizontal,
  Trash2,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Upload,
  FileWarning,
  Eye,
  RefreshCw,
  Download,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "../../lib/utils";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardContent } from "../ui/card";
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
import type { Document } from "../../types";
import { UploadDialog } from "./upload-dialog";

const FILE_ICONS: Record<string, string> = {
  pdf: "bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400",
  docx: "bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400",
  pptx: "bg-orange-50 text-orange-600 dark:bg-orange-950 dark:text-orange-400",
  xlsx: "bg-green-50 text-green-600 dark:bg-green-950 dark:text-green-400",
  csv: "bg-green-50 text-green-600 dark:bg-green-950 dark:text-green-400",
  md: "bg-purple-50 text-purple-600 dark:bg-purple-950 dark:text-purple-400",
  html: "bg-cyan-50 text-cyan-600 dark:bg-cyan-950 dark:text-cyan-400",
  json: "bg-amber-50 text-amber-600 dark:bg-amber-950 dark:text-amber-400",
  txt: "bg-surface-100 text-surface-600 dark:bg-surface-800 dark:text-surface-400",
};

const STATUS_CONFIG: Record<string, { label: string; variant: "success" | "warning" | "destructive" | "default" }> = {
  completed: { label: "Completed", variant: "success" },
  processing: { label: "Processing", variant: "warning" },
  pending: { label: "Pending", variant: "default" },
  failed: { label: "Failed", variant: "destructive" },
  cancelled: { label: "Cancelled", variant: "default" },
  queued: { label: "Queued", variant: "default" },
};

interface DocumentListProps {
  documents: Document[];
  total: number;
  page: number;
  pageSize: number;
  loading?: boolean;
  searchQuery: string;
  statusFilter: string;
  sortBy: string;
  sortOrder: "asc" | "desc";
  onSearchChange: (query: string) => void;
  onStatusFilterChange: (status: string) => void;
  onSortChange: (sortBy: string) => void;
  onPageChange: (page: number) => void;
  onDelete: (id: string) => void;
  onUpload: (files: File[]) => Promise<void>;
}

export function DocumentList({
  documents,
  total,
  page,
  pageSize,
  loading,
  searchQuery,
  statusFilter,
  sortBy,
  sortOrder,
  onSearchChange,
  onStatusFilterChange,
  onSortChange,
  onPageChange,
  onDelete,
  onUpload,
}: DocumentListProps) {
  const navigate = useNavigate();
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set());
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  const totalPages = Math.ceil(total / pageSize);

  const toggleSelect = useCallback((id: string) => {
    setSelectedDocs((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (selectedDocs.size === documents.length) {
      setSelectedDocs(new Set());
    } else {
      setSelectedDocs(new Set(documents.map((d) => d.id)));
    }
  }, [selectedDocs, documents]);

  const getFileIcon = (fileType: string) => {
    const type = fileType?.toLowerCase();
    return FILE_ICONS[type] || "bg-surface-100 text-surface-600";
  };

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3 flex-1">
          {/* Search */}
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-surface-400" />
            <input
              type="text"
              placeholder="Search documents..."
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              className="h-9 w-full rounded-lg border border-surface-300 bg-white pl-9 pr-3 text-sm text-surface-900 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
            />
          </div>

          {/* Filter toggle */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowFilters(!showFilters)}
            className={cn(showFilters && "bg-surface-100 dark:bg-surface-700")}
          >
            <Filter className="size-4" />
            Filters
          </Button>
        </div>

        <div className="flex items-center gap-2">
          {selectedDocs.size > 0 && (
            <span className="text-xs text-surface-500">
              {selectedDocs.size} selected
            </span>
          )}
          <Button onClick={() => setShowUploadDialog(true)}>
            <Upload className="mr-2 size-4" />
            Upload
          </Button>
        </div>
      </div>

      {/* Filters */}
      <AnimatePresence>
        {showFilters && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <Card className="p-3">
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-surface-500">Status:</span>
                  {["", "completed", "processing", "pending", "failed"].map((status) => (
                    <button
                      key={status}
                      onClick={() => onStatusFilterChange(status)}
                      className={cn(
                        "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                        statusFilter === status
                          ? "bg-brand-600 text-white"
                          : "bg-surface-100 text-surface-600 hover:bg-surface-200 dark:bg-surface-800 dark:text-surface-400 dark:hover:bg-surface-700",
                      )}
                    >
                      {status ? STATUS_CONFIG[status]?.label || status : "All"}
                    </button>
                  ))}
                </div>

                <div className="h-5 w-px bg-surface-200 dark:bg-surface-700" />

                <div className="flex items-center gap-2">
                  <span className="text-xs text-surface-500">Sort:</span>
                  {[
                    { key: "created_at", label: "Date" },
                    { key: "filename", label: "Name" },
                    { key: "file_size", label: "Size" },
                    { key: "status", label: "Status" },
                  ].map((option) => (
                    <button
                      key={option.key}
                      onClick={() => onSortChange(option.key)}
                      className={cn(
                        "flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium transition-colors",
                        sortBy === option.key
                          ? "bg-brand-50 text-brand-700 dark:bg-brand-950 dark:text-brand-300"
                          : "text-surface-500 hover:text-surface-700 dark:hover:text-surface-300",
                      )}
                    >
                      {option.label}
                      {sortBy === option.key && (
                        <ArrowUpDown className="size-3" />
                      )}
                    </button>
                  ))}
                </div>
              </div>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Document table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="space-y-0">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex items-center gap-4 px-5 py-4">
                  <Skeleton className="size-10 rounded-lg" />
                  <div className="flex-1 space-y-1">
                    <Skeleton className="h-4 w-48" />
                    <Skeleton className="h-3 w-32" />
                  </div>
                  <Skeleton className="h-5 w-20 rounded-full" />
                </div>
              ))}
            </div>
          ) : documents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16">
              <FileText className="mb-3 size-12 text-surface-300 dark:text-surface-600" />
              <h3 className="text-lg font-semibold text-surface-900 dark:text-surface-100">
                No documents yet
              </h3>
              <p className="mt-1 text-sm text-surface-500">
                Upload your first document to get started
              </p>
              <Button className="mt-4" onClick={() => setShowUploadDialog(true)}>
                <Upload className="mr-2 size-4" />
                Upload Document
              </Button>
            </div>
          ) : (
            <>
              {/* Table header */}
              <div className="hidden border-b border-surface-100 px-5 py-2.5 lg:flex dark:border-surface-700">
                <div className="flex w-10 items-center">
                  <input
                    type="checkbox"
                    checked={selectedDocs.size === documents.length && documents.length > 0}
                    onChange={toggleSelectAll}
                    className="rounded border-surface-300 text-brand-600 focus:ring-brand-500"
                  />
                </div>
                <div className="flex-1 grid grid-cols-12 gap-3 text-xs font-medium text-surface-500 uppercase tracking-wider">
                  <span className="col-span-4">Name</span>
                  <span className="col-span-2">Type</span>
                  <span className="col-span-2">Status</span>
                  <span className="col-span-2">Size / Pages</span>
                  <span className="col-span-2">Date</span>
                </div>
              </div>

              {/* Table body */}
              <div className="divide-y divide-surface-100 dark:divide-surface-700">
                <AnimatePresence>
                  {documents.map((doc) => {
                    const ext = doc.file_type?.toLowerCase();
                    const statusCfg = STATUS_CONFIG[doc.status] || { label: doc.status, variant: "default" as const };

                    return (
                      <motion.div
                        key={doc.id}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className={cn(
                          "flex items-center gap-4 px-5 py-3.5 transition-all duration-200 cursor-pointer hover:bg-surface-50 dark:hover:bg-surface-750",
                          selectedDocs.has(doc.id) && "bg-brand-50/50 dark:bg-brand-950/30",
                        )}
                      >
                        {/* Checkbox */}
                        <div className="flex w-10 shrink-0 items-center">
                          <input
                            type="checkbox"
                            checked={selectedDocs.has(doc.id)}
                            onChange={() => toggleSelect(doc.id)}
                            onClick={(e) => e.stopPropagation()}
                            className="rounded border-surface-300 text-brand-600 focus:ring-brand-500"
                          />
                        </div>

                        {/* File icon + name */}
                        <div
                          className="flex-1 min-w-0 grid grid-cols-12 gap-3 items-center"
                          onClick={() => navigate(`/documents/${doc.id}`)}
                        >
                          <div className="col-span-4 flex items-center gap-3 min-w-0">
                            <div
                              className={cn(
                                "flex size-9 shrink-0 items-center justify-center rounded-lg",
                                getFileIcon(doc.file_type),
                              )}
                            >
                              <FileText className="size-4.5" />
                            </div>
                            <div className="min-w-0">
                              <p className="truncate text-sm font-medium text-surface-900 dark:text-surface-100">
                                {doc.title || doc.filename}
                              </p>
                              <p className="text-xs text-surface-500 truncate">
                                {doc.filename}
                              </p>
                            </div>
                          </div>

                          <div className="col-span-2">
                            <span className="text-xs text-surface-500">
                              {ext?.toUpperCase()}
                            </span>
                          </div>

                          <div className="col-span-2">
                            <Badge
                              variant={statusCfg.variant}
                              className="text-[10px]"
                            >
                              {statusCfg.label}
                            </Badge>
                          </div>

                          <div className="col-span-2">
                            <span className="text-xs text-surface-500">
                              {doc.file_size
                                ? `${(doc.file_size / 1024 / 1024).toFixed(1)} MB`
                                : "-"}
                              {doc.pages ? ` · ${doc.pages}p` : ""}
                            </span>
                          </div>

                          <div className="col-span-2">
                            <span className="text-xs text-surface-400">
                              {doc.created_at
                                ? new Date(doc.created_at).toLocaleDateString()
                                : "-"}
                            </span>
                          </div>
                        </div>

                        {/* Actions */}
                        <div className="flex shrink-0 items-center gap-1">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate(`/documents/${doc.id}`);
                            }}
                            className="rounded p-1.5 text-surface-400 hover:bg-surface-100 hover:text-surface-600 dark:hover:bg-surface-700 dark:hover:text-surface-300"
                            title="View details"
                          >
                            <Eye className="size-4" />
                          </button>
                          <div className="relative group">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setDeleteTarget(doc.id);
                              }}
                              className="rounded p-1.5 text-surface-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950 dark:hover:text-red-400"
                              title="Delete"
                            >
                              <Trash2 className="size-4" />
                            </button>
                          </div>
                        </div>
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-surface-500">
            Showing {(page - 1) * pageSize + 1}-{Math.min(page * pageSize, total)} of {total}{" "}
            documents
          </p>
          <div className="flex items-center gap-1">
            <button
              onClick={() => onPageChange(page - 1)}
              disabled={page <= 1}
              className="rounded-lg px-3 py-1.5 text-sm text-surface-600 hover:bg-surface-100 disabled:opacity-40 dark:text-surface-400 dark:hover:bg-surface-700"
            >
              Previous
            </button>
            {Array.from({ length: Math.min(totalPages, 5) }).map((_, i) => {
              const pageNum = Math.max(1, Math.min(page - 2, totalPages - 4)) + i;
              if (pageNum > totalPages) return null;
              return (
                <button
                  key={pageNum}
                  onClick={() => onPageChange(pageNum)}
                  className={cn(
                    "flex size-8 items-center justify-center rounded-lg text-sm",
                    pageNum === page
                      ? "bg-brand-600 text-white"
                      : "text-surface-600 hover:bg-surface-100 dark:text-surface-400 dark:hover:bg-surface-700",
                  )}
                >
                  {pageNum}
                </button>
              );
            })}
            <button
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages}
              className="rounded-lg px-3 py-1.5 text-sm text-surface-600 hover:bg-surface-100 disabled:opacity-40 dark:text-surface-400 dark:hover:bg-surface-700"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Upload dialog */}
      <UploadDialog
        open={showUploadDialog}
        onOpenChange={setShowUploadDialog}
        onUpload={onUpload}
      />

      {/* Delete dialog */}
      <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Document</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this document? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (deleteTarget) {
                  onDelete(deleteTarget);
                  setDeleteTarget(null);
                }
              }}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
