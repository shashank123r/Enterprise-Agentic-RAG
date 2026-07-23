"""Create a test PDF for RAG pipeline verification."""

from fpdf import FPDF

pdf = FPDF()

# Page 1 - System Architecture
pdf.add_page()
pdf.set_font('Helvetica', 'B', 20)
pdf.cell(0, 15, 'Enterprise RAG Platform', new_x="LMARGIN", new_y="NEXT", align='C')
pdf.set_font('Helvetica', 'I', 14)
pdf.cell(0, 10, 'Technical Documentation v2.0', new_x="LMARGIN", new_y="NEXT", align='C')
pdf.ln(8)
pdf.set_font('Helvetica', 'B', 12)
pdf.cell(0, 8, '1. System Architecture', new_x="LMARGIN", new_y="NEXT")
pdf.set_font('Helvetica', '', 11)
text = (
    "The Enterprise RAG Platform uses a microservices architecture with "
    "FastAPI for the backend API, PostgreSQL for metadata storage, Redis for "
    "caching and message queuing, and Milvus for vector storage. "
    "NVIDIA NIM provides hosted API endpoints for embedding generation using "
    "nv-embed-v1, reranking using nv-rerank-qa-4, and LLM chat using "
    "Llama 3.1 70B Instruct. The frontend is built with React 18, "
    "TypeScript, Vite, and Tailwind CSS."
)
pdf.multi_cell(0, 6, text)
pdf.ln(6)
pdf.set_font('Helvetica', 'B', 12)
pdf.cell(0, 8, '2. Key Components', new_x="LMARGIN", new_y="NEXT")
pdf.set_font('Helvetica', '', 11)
components = (
    "- FastAPI Backend: RESTful API for document management, indexing, retrieval, and RAG\n"
    "- PostgreSQL: Document metadata, user accounts, ingestion jobs, chunk records\n"
    "- Redis: Caching, rate limiting, ARQ message queuing for background jobs\n"
    "- Milvus: High-performance vector database with IVF_FLAT indexing\n"
    "- NVIDIA NIM: Embeddings (nv-embed-v1, 1024-dim), Reranking (nv-rerank-qa-4), LLM (Llama 3.1 70B)"
)
pdf.multi_cell(0, 6, components)
pdf.ln(6)

# Page 2 - Document Processing Pipeline
pdf.add_page()
pdf.set_font('Helvetica', 'B', 16)
pdf.cell(0, 12, '3. Document Processing Pipeline', new_x="LMARGIN", new_y="NEXT")
pdf.ln(4)
pdf.set_font('Helvetica', '', 11)
stages = (
    "Documents uploaded to the platform go through processing stages:\n\n"
    "Stage 1 - File Validation: Validates file size (max 100MB), MIME type detection\n"
    "via python-magic, and corruption checking. Supports PDF, DOCX, PPTX, XLSX, CSV.\n\n"
    "Stage 2 - Text Extraction: Specialized extractors for each format. PDFs use\n"
    "PyMuPDF (fitz) for text extraction. Tables and embedded images are also extracted.\n\n"
    "Stage 3 - OCR: Scanned PDFs are detected and processed using Tesseract OCR via\n"
    "pytesseract. pdf2image converts PDF pages to images for OCR processing.\n\n"
    "Stage 4 - Text Cleaning: Multi-stage pipeline with Unicode normalization (NFC),\n"
    "whitespace normalization, header/footer removal, page number removal.\n\n"
    "Stage 5 - Language Detection: Uses langdetect library. Supports English, Spanish,\n"
    "French, German, Chinese, Japanese, and 50+ languages.\n\n"
    "Stage 6 - Chunking: Adaptive chunking strategy adjusts chunk size based on content\n"
    "density. Also supports semantic chunking at sentence boundaries, heading-aware\n"
    "chunking by document sections, markdown-aware chunking, table-aware chunking\n"
    "keeping tables intact, and parent-child chunking for hierarchical relationships.\n\n"
    "Stage 7 - Storage: Chunks, tables, and images are stored in PostgreSQL via\n"
    "SQLAlchemy ORM with batch inserts for performance."
)
pdf.multi_cell(0, 6, stages)
pdf.ln(6)

# Page 3 - Embeddings and Vector Search
pdf.add_page()
pdf.set_font('Helvetica', 'B', 16)
pdf.cell(0, 12, '4. Embeddings and Vector Search', new_x="LMARGIN", new_y="NEXT")
pdf.ln(4)
pdf.set_font('Helvetica', '', 11)
embed = (
    "Embedding Generation:\n\n"
    "The platform generates embeddings using NVIDIA NIM endpoints. The default model\n"
    "nvidia/nv-embed-v1 produces 1024-dimensional vectors. The system batches texts\n"
    "in groups of 32 with concurrent requests limited to 10 via semaphore. Retry with\n"
    "exponential backoff handles transient failures.\n\n"
    "Embedding Cache:\n\n"
    "To reduce API costs, embeddings are cached in Redis with 24-hour TTL. Cache keys\n"
    "incorporate the text checksum and model name. Cache is invalidated on re-indexing.\n\n"
    "Vector Storage (Milvus):\n\n"
    "Milvus stores embeddings with metadata: chunk_id (UUID), document_id (UUID),\n"
    "text content, page number, chunk_index, section_title, language, checksum\n"
    "(SHA-256), version, source filename, and embedding_model name. IVF_FLAT index\n"
    "with COSINE similarity metric is used for efficient ANN search.\n\n"
    "Retrieval Methods:\n\n"
    "1. Dense Retrieval: Cosine similarity between query and chunk embeddings\n"
    "2. BM25 Retrieval: Keyword-based exact term matching with inverted index\n"
    "3. Hybrid Retrieval: Combines dense and BM25 using Reciprocal Rank Fusion (RRF)\n"
    "4. Parent-Child Retrieval: Small child chunks for precision, parent chunks for context"
)
pdf.multi_cell(0, 6, embed)
pdf.ln(6)

# Page 4 - RAG Pipeline
pdf.add_page()
pdf.set_font('Helvetica', 'B', 16)
pdf.cell(0, 12, '5. RAG Pipeline', new_x="LMARGIN", new_y="NEXT")
pdf.ln(4)
pdf.set_font('Helvetica', '', 11)
rag = (
    "The RAG pipeline answers questions using these steps:\n\n"
    "Step 1 - Query Processing: User question is optionally rewritten for better\n"
    "retrieval. The query is embedded using the same nv-embed-v1 model.\n\n"
    "Step 2 - Retrieval: Embedded query searches Milvus with configurable top_k\n"
    "(default 10), metadata filters, and minimum score thresholds.\n\n"
    "Step 3 - Reranking: Retrieved chunks are reranked using NVIDIA nv-rerank-qa-4\n"
    "cross-encoder for improved relevance.\n\n"
    "Step 4 - Context Building: Chunks are assembled into a context window respecting\n"
    "token budget (max 4096 context tokens). Considers scores, relevance, and diversity.\n\n"
    "Step 5 - Prompt Construction: Structured prompt with context, conversation\n"
    "history, and question. LLM is instructed to answer based only on provided context.\n\n"
    "Step 6 - LLM Generation: Prompt sent to NVIDIA NIM hosted Llama 3.1 70B Instruct.\n"
    "Supports streaming token-by-token via SSE.\n\n"
    "Step 7 - Grounding Validation: Answer validated against retrieved context.\n"
    "Unsupported statements are flagged.\n\n"
    "Step 8 - Citation Building: Maps answer parts to supporting chunks with structured\n"
    "citations including document title, page number, and section.\n\n"
    "Step 9 - Response: Includes answer text, citations, chunk references, grounding\n"
    "status, and performance metrics (retrieval time, LLM time, total time)."
)
pdf.multi_cell(0, 6, rag)
pdf.ln(6)

# Page 5 - Security
pdf.add_page()
pdf.set_font('Helvetica', 'B', 16)
pdf.cell(0, 12, '6. Security and Authentication', new_x="LMARGIN", new_y="NEXT")
pdf.ln(4)
pdf.set_font('Helvetica', '', 11)
security = (
    "Authentication:\n\n"
    "JWT-based authentication with access tokens (30 min expiry) and refresh tokens\n"
    "(7 days). Tokens are signed with HS256 algorithm. Password hashing uses bcrypt\n"
    "with 12 rounds.\n\n"
    "Authorization:\n\n"
    "Role-based access control with Admin and User roles. Admins can access all\n"
    "documents; users access their own. Endpoints enforce authorization via middleware.\n\n"
    "Rate Limiting:\n\n"
    "60 requests per minute per user with burst allowance of 100. Redis-based rate\n"
    "limiting with sliding window.\n\n"
    "API Key Management:\n\n"
    "NVIDIA NIM API key configuration through environment variables. CORS\n"
    "configuration allows localhost origins."
)
pdf.multi_cell(0, 6, security)
pdf.ln(6)
pdf.set_font('Helvetica', 'B', 12)
pdf.cell(0, 8, '7. API Endpoints', new_x="LMARGIN", new_y="NEXT")
pdf.set_font('Helvetica', '', 11)
api = (
    "POST /api/v1/auth/register - User registration with email, username, password\n"
    "POST /api/v1/auth/login - Login returning JWT tokens\n"
    "POST /api/v1/upload - Document upload with MIME validation\n"
    "POST /api/v1/indexing/start - Start document indexing pipeline\n"
    "POST /api/v1/retrieval/search - Search with dense, BM25, or hybrid methods\n"
    "POST /api/v1/chat - RAG question answering with citations\n"
    "DELETE /api/v1/documents/{id} - Soft delete document"
)
pdf.multi_cell(0, 6, api)
pdf.ln(6)

# Page 6 - Configuration
pdf.add_page()
pdf.set_font('Helvetica', 'B', 16)
pdf.cell(0, 12, '8. Configuration and Environment', new_x="LMARGIN", new_y="NEXT")
pdf.ln(4)
pdf.set_font('Helvetica', '', 11)
config = (
    "Environment Variables:\n\n"
    "POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB\n"
    "- PostgreSQL connection settings\n\n"
    "REDIS_HOST, REDIS_PORT, REDIS_PASSWORD - Redis connection settings\n\n"
    "MILVUS_HOST, MILVUS_PORT - Milvus connection (default localhost:19530)\n\n"
    "NVIDIA_NIM_API_KEY - API key for NVIDIA NIM hosted services\n\n"
    "EMBEDDING_MODEL - Model name (default: nvidia/nv-embed-v1)\n\n"
    "EMBEDDING_PROVIDER - Provider type (default: nvidia_nim)\n\n"
    "VECTOR_STORE_PROVIDER - Vector DB type (default: milvus)\n\n"
    "JWT_SECRET_KEY - JWT signing key (min 32 chars)\n\n"
    "MAX_UPLOAD_SIZE_MB - Max file upload size (default: 100MB)\n\n"
    "Deployment:\n\n"
    "Docker Compose orchestrates api, postgres, and redis containers. The FastAPI\n"
    "app is built as a Python wheel during Docker build. All services share a Docker\n"
    "network for communication."
)
pdf.multi_cell(0, 6, config)

pdf.output('test_doc.pdf')
print(f"Created test_doc.pdf - {pdf.pages_count} pages, {len(pdf.pages)} pages data")
