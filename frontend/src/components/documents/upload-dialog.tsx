import { useState, useCallback, useRef } from "react";
import {
  Upload,
  X,
  FileText,
  CheckCircle2,
  AlertCircle,
  Loader2,
  FileWarning,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Progress } from "../ui/progress";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "../ui/dialog";

const ACCEPTED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "text/csv",
  "text/markdown",
  "text/html",
  "application/json",
  "text/plain",
];

const MAX_FILE_SIZE = 100 * 1024 * 1024; // 100 MB

interface UploadFile {
  file: File;
  id: string;
  progress: number;
  status: "pending" | "uploading" | "completed" | "failed";
  error?: string;
}

interface UploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpload: (files: File[]) => Promise<void>;
}

export function UploadDialog({ open, onOpenChange, onUpload }: UploadDialogProps) {
  const [uploadFiles, setUploadFiles] = useState<UploadFile[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback((incoming: File[]) => {
    const newFiles: UploadFile[] = incoming.map((file) => ({
      file,
      id: crypto.randomUUID(),
      progress: 0,
      status: "pending" as const,
    }));
    setUploadFiles((prev) => [...prev, ...newFiles]);
  }, []);

  const removeFile = useCallback((id: string) => {
    setUploadFiles((prev) => prev.filter((f) => f.id !== id));
  }, []);

  const validateFile = useCallback((file: File): string | null => {
    if (!ACCEPTED_TYPES.includes(file.type)) {
      return `Unsupported file type: ${file.type || "unknown"}`;
    }
    if (file.size > MAX_FILE_SIZE) {
      return `File too large: ${(file.size / 1024 / 1024).toFixed(1)} MB (max 100 MB)`;
    }
    return null;
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const files = Array.from(e.dataTransfer.files).filter((f) => !validateFile(f));
      if (files.length > 0) addFiles(files);
    },
    [addFiles, validateFile],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files) {
        addFiles(Array.from(e.target.files));
      }
    },
    [addFiles],
  );

  const handleUpload = useCallback(async () => {
    if (uploadFiles.length === 0) return;

    setIsUploading(true);
    setUploadFiles((prev) =>
      prev.map((f) => (f.status === "pending" ? { ...f, status: "uploading" as const } : f)),
    );

    try {
      await onUpload(uploadFiles.map((f) => f.file));
      setUploadFiles((prev) =>
        prev.map((f) => ({ ...f, status: "completed" as const, progress: 100 })),
      );
      setTimeout(() => {
        onOpenChange(false);
        setUploadFiles([]);
      }, 1500);
    } catch {
      setUploadFiles((prev) =>
        prev.map((f) =>
          f.status === "uploading"
            ? { ...f, status: "failed" as const, error: "Upload failed" }
            : f,
        ),
      );
    } finally {
      setIsUploading(false);
    }
  }, [uploadFiles, onUpload, onOpenChange]);

  const handleClose = useCallback(() => {
    if (isUploading) return;
    setUploadFiles([]);
    onOpenChange(false);
  }, [isUploading, onOpenChange]);

  const hasInvalidFiles = uploadFiles.some((f) => validateFile(f.file));

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Upload Documents</DialogTitle>
          <DialogDescription>
            Upload documents to your knowledge base. Supported: PDF, DOCX, PPTX, XLSX, CSV, MD,
            HTML, JSON, TXT
          </DialogDescription>
        </DialogHeader>

        {/* Drop zone */}
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => inputRef.current?.click()}
          className={cn(
            "relative cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-all duration-200",
            isDragging
              ? "border-brand-500 bg-brand-50 dark:border-brand-400 dark:bg-brand-950"
              : "border-surface-300 hover:border-surface-400 dark:border-surface-600 dark:hover:border-surface-500",
          )}
        >
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.pptx,.xlsx,.csv,.md,.html,.json,.txt"
            className="hidden"
            onChange={handleFileSelect}
          />
          <Upload
            className={cn(
              "mx-auto mb-3 size-8 transition-colors",
              isDragging ? "text-brand-600 dark:text-brand-400" : "text-surface-400",
            )}
          />
          <p className="text-sm font-medium text-surface-700 dark:text-surface-300">
            {isDragging ? "Drop files here" : "Drag & drop files or click to browse"}
          </p>
          <p className="mt-1 text-xs text-surface-500">
            PDF, DOCX, PPTX, XLSX, CSV, MD, HTML, JSON, TXT &mdash; up to 100 MB each
          </p>
        </div>

        {/* File queue */}
        {uploadFiles.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-surface-500">
              {uploadFiles.length} file(s) selected
            </p>
            <div className="max-h-48 space-y-2 overflow-y-auto">
              <AnimatePresence>
                {uploadFiles.map((file) => (
                  <motion.div
                    key={file.id}
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="flex items-center gap-3 rounded-lg border border-surface-200 bg-surface-50 p-3 dark:border-surface-700 dark:bg-surface-800/50"
                  >
                    <FileText className="size-5 shrink-0 text-surface-400" />
                    <div className="flex-1 min-w-0">
                      <p className="truncate text-sm font-medium text-surface-900 dark:text-surface-100">
                        {file.file.name}
                      </p>
                      <p className="text-xs text-surface-500">
                        {(file.file.size / 1024 / 1024).toFixed(1)} MB
                      </p>
                      {file.status === "uploading" && (
                        <Progress value={file.progress} className="mt-1 h-1" />
                      )}
                      {file.status === "failed" && file.error && (
                        <p className="mt-0.5 text-xs text-red-500">{file.error}</p>
                      )}
                    </div>
                    <div className="shrink-0">
                      {file.status === "completed" && (
                        <CheckCircle2 className="size-5 text-green-500" />
                      )}
                      {file.status === "failed" && (
                        <AlertCircle className="size-5 text-red-500" />
                      )}
                      {file.status === "uploading" && (
                        <Loader2 className="size-5 animate-spin text-brand-500" />
                      )}
                      {file.status === "pending" && !isUploading && (
                        <button
                          onClick={() => removeFile(file.id)}
                          className="rounded p-1 text-surface-400 hover:bg-surface-200 hover:text-surface-600 dark:hover:bg-surface-700 dark:hover:text-surface-300"
                        >
                          <X className="size-4" />
                        </button>
                      )}
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-end gap-2">
          <Button variant="outline" onClick={handleClose} disabled={isUploading}>
            Cancel
          </Button>
          <Button
            onClick={handleUpload}
            disabled={uploadFiles.length === 0 || isUploading || hasInvalidFiles}
          >
            {isUploading ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                Uploading...
              </>
            ) : (
              <>
                <Upload className="mr-2 size-4" />
                Upload {uploadFiles.length > 0 ? `(${uploadFiles.length})` : ""}
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
