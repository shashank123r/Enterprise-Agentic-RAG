import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { FileText } from "lucide-react";
import { useLayoutStore } from "../store";
import { DocumentList } from "../components/documents/document-list";
import { useDocumentsList, useDeleteDocument, useUploadDocuments } from "../hooks/useDocuments";

export function DocumentsPage() {
  const navigate = useNavigate();
  const setPageTitle = useLayoutStore((s) => s.setPageTitle);

  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  const queryParams = {
    page,
    page_size: 20,
    search: searchQuery || undefined,
    status: statusFilter || undefined,
    sort_by: sortBy,
    sort_order: sortOrder,
  };

  const { data, isLoading } = useDocumentsList(queryParams);
  const deleteMutation = useDeleteDocument();
  const uploadMutation = useUploadDocuments();

  useEffect(() => {
    setPageTitle("Documents");
  }, [setPageTitle]);

  const handleSearchChange = useCallback((query: string) => {
    setSearchQuery(query);
    setPage(1);
  }, []);

  const handleStatusFilterChange = useCallback((status: string) => {
    setStatusFilter(status);
    setPage(1);
  }, []);

  const handleSortChange = useCallback(
    (newSortBy: string) => {
      if (newSortBy === sortBy) {
        setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
      } else {
        setSortBy(newSortBy);
        setSortOrder("desc");
      }
    },
    [sortBy],
  );

  const handlePageChange = useCallback((newPage: number) => {
    setPage(newPage);
  }, []);

  const handleDelete = useCallback(
    (id: string) => {
      deleteMutation.mutate(id);
    },
    [deleteMutation],
  );

  const handleUpload = useCallback(
    async (files: File[]) => {
      await uploadMutation.mutateAsync({ files });
      setPage(1);
    },
    [uploadMutation],
  );

  return (
    <div className="flex flex-col gap-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div className="flex items-start gap-4">
          <div className="flex size-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-950 dark:text-brand-400">
            <FileText className="size-5" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-surface-900 dark:text-surface-50">
              Documents
            </h1>
            <p className="mt-1 text-sm text-surface-500">
              Upload and manage your enterprise knowledge base documents
            </p>
          </div>
        </div>
      </div>

      {/* Stats cards */}
      {data && data.total > 0 && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[
            { label: "Total Documents", value: data.total },
            {
              label: "Processed",
              value: data.items.filter((d) => d.status === "completed").length,
              color: "text-green-600 dark:text-green-400",
            },
            {
              label: "Processing",
              value: data.items.filter((d) => d.status === "processing").length,
              color: "text-amber-600 dark:text-amber-400",
            },
            {
              label: "Failed",
              value: data.items.filter((d) => d.status === "failed").length,
              color: "text-red-600 dark:text-red-400",
            },
          ].map((stat) => (
            <div
              key={stat.label}
              className="rounded-xl border border-surface-200 bg-white p-4 dark:border-surface-700 dark:bg-surface-800"
            >
              <p className="text-xs text-surface-500">{stat.label}</p>
              <p
                className={`mt-1 text-2xl font-bold ${
                  stat.color || "text-surface-900 dark:text-surface-50"
                }`}
              >
                {stat.value}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Document list */}
      <DocumentList
        documents={data?.items || []}
        total={data?.total || 0}
        page={page}
        pageSize={20}
        loading={isLoading}
        searchQuery={searchQuery}
        statusFilter={statusFilter}
        sortBy={sortBy}
        sortOrder={sortOrder}
        onSearchChange={handleSearchChange}
        onStatusFilterChange={handleStatusFilterChange}
        onSortChange={handleSortChange}
        onPageChange={handlePageChange}
        onDelete={handleDelete}
        onUpload={handleUpload}
      />
    </div>
  );
}
