import { useState } from "react";
import { Search, Hash, BookOpen, FileText, ArrowRight } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "../../lib/utils";
import { Badge } from "../ui/badge";
import type { DocumentChunk } from "../../services/document.service";

interface ChunkViewerProps {
  chunks: DocumentChunk[];
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onSearch?: (query: string) => void;
  loading?: boolean;
}

export function ChunkViewer({
  chunks,
  total,
  page,
  pageSize,
  onPageChange,
  onSearch,
  loading,
}: ChunkViewerProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedChunk, setSelectedChunk] = useState<string | null>(null);

  const totalPages = Math.ceil(total / pageSize);

  const handleSearch = (value: string) => {
    setSearchQuery(value);
    onSearch?.(value);
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-surface-400" />
        <input
          type="text"
          placeholder="Search chunks..."
          value={searchQuery}
          onChange={(e) => handleSearch(e.target.value)}
          className="h-9 w-full rounded-lg border border-surface-300 bg-white pl-9 pr-3 text-sm text-surface-900 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-surface-600 dark:bg-surface-800 dark:text-surface-100"
        />
      </div>

      {/* Chunk list */}
      <div className="space-y-2">
        <AnimatePresence>
          {chunks.map((chunk) => (
            <motion.div
              key={chunk.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              onClick={() => setSelectedChunk(selectedChunk === chunk.id ? null : chunk.id)}
              className={cn(
                "cursor-pointer rounded-lg border p-3 transition-all duration-200",
                selectedChunk === chunk.id
                  ? "border-brand-500 bg-brand-50 dark:border-brand-400 dark:bg-brand-950"
                  : "border-surface-200 bg-white hover:border-surface-300 dark:border-surface-700 dark:bg-surface-800 dark:hover:border-surface-600",
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 text-xs text-surface-500">
                    <span className="flex items-center gap-1">
                      <Hash className="size-3" />
                      {chunk.id.slice(0, 8)}
                    </span>
                    {chunk.page > 0 && (
                      <span className="flex items-center gap-1">
                        <BookOpen className="size-3" />
                        p.{chunk.page}
                      </span>
                    )}
                    {chunk.section && (
                      <Badge variant="outline" className="text-[10px]">
                        {chunk.section}
                      </Badge>
                    )}
                    <span className="text-surface-400">{chunk.token_count} tokens</span>
                  </div>
                  <p
                    className={cn(
                      "mt-1 text-sm leading-relaxed",
                      selectedChunk === chunk.id
                        ? "text-surface-900 dark:text-surface-50"
                        : "text-surface-600 line-clamp-3 dark:text-surface-400",
                    )}
                  >
                    {chunk.text}
                  </p>
                </div>
                <ArrowRight
                  className={cn(
                    "mt-1 size-4 shrink-0 transition-transform",
                    selectedChunk === chunk.id ? "rotate-90 text-brand-500" : "text-surface-300",
                  )}
                />
              </div>

              {/* Expanded metadata */}
              {selectedChunk === chunk.id && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  className="mt-3 border-t border-surface-200 pt-3 dark:border-surface-700"
                >
                  <div className="grid grid-cols-2 gap-2 text-xs text-surface-500">
                    <div>
                      <span className="font-medium text-surface-700 dark:text-surface-300">Chunk ID:</span>{" "}
                      {chunk.id}
                    </div>
                    {chunk.parent_id && (
                      <div>
                        <span className="font-medium text-surface-700 dark:text-surface-300">
                          Parent:
                        </span>{" "}
                        {chunk.parent_id.slice(0, 8)}
                      </div>
                    )}
                    <div>
                      <span className="font-medium text-surface-700 dark:text-surface-300">
                        Position:
                      </span>{" "}
                      {chunk.position}
                    </div>
                    <div>
                      <span className="font-medium text-surface-700 dark:text-surface-300">
                        Language:
                      </span>{" "}
                      {chunk.language}
                    </div>
                    {chunk.heading && (
                      <div className="col-span-2">
                        <span className="font-medium text-surface-700 dark:text-surface-300">
                          Heading:
                        </span>{" "}
                        {chunk.heading}
                      </div>
                    )}
                    {chunk.metadata && Object.keys(chunk.metadata).length > 0 && (
                      <div className="col-span-2">
                        <span className="font-medium text-surface-700 dark:text-surface-300">
                          Metadata:
                        </span>{" "}
                        <pre className="mt-1 overflow-x-auto rounded bg-surface-100 p-2 text-xs dark:bg-surface-700">
                          {JSON.stringify(chunk.metadata, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-surface-200 pt-3 dark:border-surface-700">
          <p className="text-xs text-surface-500">
            {total} chunk{total !== 1 ? "s" : ""}
          </p>
          <div className="flex items-center gap-1">
            <button
              onClick={() => onPageChange(page - 1)}
              disabled={page <= 1}
              className="rounded px-2 py-1 text-xs text-surface-600 hover:bg-surface-100 disabled:opacity-40 dark:text-surface-400 dark:hover:bg-surface-700"
            >
              Previous
            </button>
            <span className="px-2 text-xs text-surface-500">
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages}
              className="rounded px-2 py-1 text-xs text-surface-600 hover:bg-surface-100 disabled:opacity-40 dark:text-surface-400 dark:hover:bg-surface-700"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
