export * from "./auth";

// ── API Error ────────────────────────────────

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

// ── Pagination ───────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

// ── Health ───────────────────────────────────

export interface HealthCheck {
  status: string;
  version: string;
  environment: string;
  checks: Record<string, string>;
}

export interface MessageResponse {
  message: string;
  code: string;
}

// ── Document ─────────────────────────────────

export type DocumentStatus = "pending" | "processing" | "completed" | "failed";

export interface Document {
  id: string;
  filename: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  checksum: string;
  status: DocumentStatus;
  title: string | null;
  author: string | null;
  language: string | null;
  page_count: number;
  table_count: number;
  image_count: number;
  chunk_count: number;
  ocr_used: boolean;
  metadata: Record<string, unknown>;
  current_version: number;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}

export interface DocumentUploadResponse {
  document: Document;
  job: IngestionJobStatus;
}

export type IngestionJobStage = "queued" | "extracting" | "ocr_check" | "cleaning" | "detecting_language" | "chunking" | "storing" | "completed" | "failed" | "cancelled";

export interface IngestionJobStatus {
  job_id: string;
  document_id: string;
  status: string;
  progress: number;
  current_stage: string | null;
  error_message: string | null;
  retry_count: number;
  max_retries: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface DocumentChunk {
  id: string;
  chunk_index: number;
  content: string;
  page_number: number | null;
  section_title: string | null;
  chunk_type: string;
  language: string | null;
  token_count: number;
  char_count: number;
  metadata: Record<string, unknown>;
}

export interface DocumentTable {
  id: string;
  page_number: number | null;
  table_index: number;
  caption: string | null;
  csv_representation: string;
  html_representation: string | null;
  row_count: number;
  column_count: number;
}

export interface DocumentImage {
  id: string;
  page_number: number | null;
  image_index: number;
  image_path: string;
  caption: string | null;
  alt_text: string | null;
  width: number | null;
  height: number | null;
  format: string | null;
}

export interface DocumentVersion {
  id: string;
  version_number: number;
  filename: string;
  size_bytes: number;
  checksum: string;
  changes: string | null;
  created_at: string;
}

export interface ExtractTextResponse {
  document_id: string;
  filename: string;
  total_chunks: number;
  total_characters: number;
  text: string;
}

export interface DocumentStats {
  document_id: string;
  filename: string;
  mime_type: string;
  status: string;
  processing_time_ms: number;
  page_count: number;
  table_count: number;
  image_count: number;
  chunk_count: number;
  ocr_used: boolean;
  language: string | null;
  extraction_errors: Record<string, unknown>[];
}

// ── Indexing Job ─────────────────────────────

export type IndexingStatus = "queued" | "processing" | "embedding" | "writing" | "completed" | "failed" | "cancelled" | "retrying";

export interface IndexingJob {
  job_id: string;
  document_id: string;
  status: IndexingStatus;
  progress_percent: number;
  total_chunks: number;
  processed_chunks: number;
  failed_chunks: number;
  error_message: string | null;
  retry_count: number;
  cache_hits: number;
  embedding_model: string;
  collection_name: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface IndexingStartResponse {
  job_id: string;
  document_id: string;
  status: string;
  collection_name: string;
  total_chunks: number;
  created_at: string;
}

export interface IndexingHealth {
  task_manager_active_tasks: number;
  use_arq: boolean;
}

export interface IndexingStats {
  counts_by_status: Record<string, number>;
  active_jobs_count: number;
  active_jobs: Array<{
    job_id: string;
    document_id: string;
    status: string;
    progress_percent: number;
  }>;
}

// ── Collection ───────────────────────────────

export interface Collection {
  name: string;
  dimension: number;
  metric_type: string;
  vector_count: number;
  status: string;
  embedding_model: string;
  description: string | null;
  created_at: string;
}

export interface CollectionDetail extends Collection {
  milvus_stats: Record<string, unknown>;
  index_info: Record<string, unknown>[];
}

// ── Retrieval ────────────────────────────────

export type RetrievalMethod = "dense" | "bm25" | "hybrid" | "parent_child";

export interface RetrievalRequest {
  query: string;
  collection_name?: string;
  top_k?: number;
  method?: RetrievalMethod;
  filters?: Record<string, unknown>;
  rerank?: boolean;
  rerank_top_k?: number;
  hybrid_alpha?: number;
  min_score?: number | null;
  query_rewrite?: boolean;
  query_expansion?: boolean;
  max_context_tokens?: number | null;
}

export interface RetrievedChunk {
  chunk_id: string;
  document_id: string;
  text: string;
  score: number;
  rerank_score: number | null;
  page_number: number | null;
  section_title: string | null;
  chunk_index: number;
  language: string | null;
  metadata: Record<string, unknown>;
  retrieval_source: string;
}

export interface RetrievalMetrics {
  total_duration_ms: number;
  vector_search_ms: number;
  bm25_search_ms: number | null;
  hybrid_fusion_ms: number | null;
  rerank_ms: number | null;
  query_rewrite_ms: number | null;
  context_build_ms: number | null;
  total_chunks_retrieved: number;
  chunks_after_rerank: number | null;
  dedup_removed: number;
  method: string;
}

export interface RetrievalResult {
  query: string;
  rewritten_query: string | null;
  chunks: RetrievedChunk[];
  citations: Citation[];
  context: string | null;
  metrics: RetrievalMetrics;
  method: string;
  total_results: number;
}

export interface Citation {
  chunk_id: string;
  document_id: string;
  document_title: string;
  source: string;
  retrieval_method: string;
  text_preview: string;
  page_number: number | null;
  section_title: string | null;
  score: number;
  rerank_score: number | null;
}

export interface BM25Status {
  index_built: boolean;
  total_docs: number;
  last_built_at: string | null;
  seconds_since_built: number | null;
  total_chunks_loaded: number;
  build_error: string | null;
  healthy: boolean;
}

// ── RAG / Chat ───────────────────────────────

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations?: CitationInfo[];
  grounding_valid?: boolean;
  created_at: string;
}

export interface RAGRequest {
  question: string;
  collection_name?: string;
  top_k?: number;
  retrieval_method?: RetrievalMethod;
  rerank?: boolean;
  query_rewrite?: boolean;
  filters?: Record<string, unknown>;
  max_context_tokens?: number | null;
  max_response_tokens?: number | null;
  temperature?: number | null;
  stream?: boolean;
  conversation_history?: Array<{ role: string; content: string }> | null;
}

export interface RAGResponse {
  answer: string;
  citations: CitationInfo[];
  chunks: RAGChunk[];
  grounding_valid: boolean;
  grounding_issues: string[];
  llm_model: string;
  total_duration_ms: number;
  retrieval_duration_ms: number;
  llm_duration_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface RAGChunk {
  chunk_id: string;
  document_id: string;
  document_title: string;
  text_preview: string;
  page_number: number | null;
  section_title: string | null;
  score: number;
  retrieval_method: string;
}

export interface CitationInfo {
  index: number;
  chunk_id: string;
  document_id: string;
  document_title: string;
  source: string;
  retrieval_method: string;
  page_number: number | null;
  section_title: string | null;
  text_preview: string;
}

// ── Embedding Health ─────────────────────────

export interface EmbeddingHealth {
  healthy: boolean;
  provider: string;
  model: string;
  latency_ms: number;
}

export interface VectorStoreHealth {
  healthy: boolean;
  provider: string;
  collections_count: number;
  collections: string[];
}

// ── Retrieval Health ─────────────────────────

export interface RetrievalHealth {
  bm25: { healthy: boolean; total_docs: number };
  dense: { healthy: boolean };
  hybrid: { healthy: boolean };
  parent_child: { healthy: boolean };
  reranker: { healthy: boolean };
  embedding_provider: { healthy: boolean; provider: string; model: string };
  vector_store: { healthy: boolean; provider: string; collections_count: number };
  retrieval_ready: boolean;
}
