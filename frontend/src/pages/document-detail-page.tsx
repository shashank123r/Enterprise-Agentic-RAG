import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FileText, AlertCircle, RefreshCw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";
import { Button } from "../components/ui/button";
import { useLayoutStore } from "../store";
import { documentService } from "../services/document.service";

const STATUS_VARIANTS: Record<string, "default" | "secondary" | "destructive" | "outline" | "success" | "warning"> = {
  completed: "success",
  processing: "warning",
  failed: "destructive",
  queued: "secondary",
  cancelled: "outline",
  embedding: "warning",
  writing: "warning",
};

export function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const setPageTitle = useLayoutStore((s) => s.setPageTitle);

  useEffect(() => {
    setPageTitle("Document Detail");
  }, [setPageTitle]);

  const { data: doc, isLoading, error } = useQuery({
    queryKey: ["document", id],
    queryFn: () => documentService.getDocument(id!),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-64" />
        <Card>
          <CardContent className="p-6">
            <div className="space-y-4">
              <Skeleton className="h-5 w-32" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (error || !doc) {
    return (
      <div className="flex flex-col gap-6">
        <Button variant="ghost" size="sm" className="w-fit" onClick={() => navigate("/documents")}>
          <ArrowLeft className="mr-1.5 size-3.5" />
          Back to Documents
        </Button>
        <Card>
          <CardContent className="flex flex-col items-center py-12 text-center">
            <AlertCircle className="mb-3 size-10 text-red-400" />
            <h3 className="text-sm font-medium text-surface-900 dark:text-surface-100">Document not found</h3>
            <p className="mt-1 text-xs text-surface-500">This document could not be loaded or does not exist.</p>
            <Button variant="outline" size="sm" className="mt-4" onClick={() => window.location.reload()}>
              <RefreshCw className="mr-1.5 size-3.5" />
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Back button */}
      <Button variant="ghost" size="sm" className="w-fit" onClick={() => navigate("/documents")}>
        <ArrowLeft className="mr-1.5 size-3.5" />
        Back to Documents
      </Button>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-start gap-4">
          <div className="flex size-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-950 dark:text-brand-400">
            <FileText className="size-5" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-surface-900 dark:text-surface-50">{doc.filename}</h1>
            <p className="mt-1 text-sm text-surface-500">
              Uploaded {new Date(doc.created_at).toLocaleString()}
            </p>
          </div>
        </div>
        <Badge variant={STATUS_VARIANTS[doc.status] ?? "default"} className="text-xs">
          {doc.status}
        </Badge>
      </div>

      {/* Metadata card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Document Metadata</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-surface-500">File Name</dt>
              <dd className="mt-0.5 font-medium text-surface-900 dark:text-surface-50">{doc.filename}</dd>
            </div>
            <div>
              <dt className="text-surface-500">Content Type</dt>
              <dd className="mt-0.5 font-medium text-surface-900 dark:text-surface-50">{doc.content_type ?? "N/A"}</dd>
            </div>
            <div>
              <dt className="text-surface-500">File Size</dt>
              <dd className="mt-0.5 font-medium text-surface-900 dark:text-surface-50">
                {doc.file_size ? `${(doc.file_size / 1024).toFixed(1)} KB` : "N/A"}
              </dd>
            </div>
            <div>
              <dt className="text-surface-500">Status</dt>
              <dd className="mt-0.5">
                <Badge variant={STATUS_VARIANTS[doc.status] ?? "default"} className="text-[10px]">
                  {doc.status}
                </Badge>
              </dd>
            </div>
            <div>
              <dt className="text-surface-500">Created</dt>
              <dd className="mt-0.5 font-medium text-surface-900 dark:text-surface-50">
                {new Date(doc.created_at).toLocaleString()}
              </dd>
            </div>
            <div>
              <dt className="text-surface-500">Updated</dt>
              <dd className="mt-0.5 font-medium text-surface-900 dark:text-surface-50">
                {new Date(doc.updated_at).toLocaleString()}
              </dd>
            </div>
            {doc.checksum && (
              <div className="col-span-2">
                <dt className="text-surface-500">Checksum</dt>
                <dd className="mt-0.5 font-mono text-xs text-surface-900 dark:text-surface-50 break-all">{doc.checksum}</dd>
              </div>
            )}
          </dl>
        </CardContent>
      </Card>

      {/* Chunks card */}
      {doc.chunks && doc.chunks.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">Text Chunks ({doc.chunks.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {doc.chunks.map((chunk, i) => (
                <div
                  key={chunk.id ?? i}
                  className="rounded-lg border border-surface-200 bg-surface-50 p-3 dark:border-surface-700 dark:bg-surface-800/50"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] font-medium text-surface-400">Chunk {chunk.chunk_index ?? i}</span>
                    {chunk.page_number && (
                      <span className="text-[10px] text-surface-400">Page {chunk.page_number}</span>
                    )}
                  </div>
                  <p className="text-xs text-surface-700 dark:text-surface-300 line-clamp-3">
                    {chunk.text_content ?? "No text content"}
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
