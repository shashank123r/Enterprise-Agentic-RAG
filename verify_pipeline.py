"""Complete RAG pipeline verification script.

Uploads a test PDF, runs ingestion, indexing, retrieval, RAG, and deletion.
"""

import asyncio
import json
import sys
import time
import httpx
from pathlib import Path


API = "http://localhost:8000/api/v1"
TOKEN = None
DOC_ID = None


async def login():
    global TOKEN
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{API}/auth/login", json={
            "email": "admin@example.com", "password": "admin1234"
        })
        assert r.status_code == 200, f"Login failed: {r.text}"
        TOKEN = r.json()["access_token"]
        print(f"[LOGIN] Got access token (HTTP {r.status_code})")


async def upload():
    global DOC_ID
    pdf_path = Path("test_doc.pdf")
    if not pdf_path.exists():
        print("[UPLOAD] test_doc.pdf not found in current directory")
        return False
    
    async with httpx.AsyncClient() as client:
        with open(pdf_path, "rb") as f:
            r = await client.post(
                f"{API}/documents/upload",
                headers={"Authorization": f"Bearer {TOKEN}"},
                files={"file": ("test_doc.pdf", f, "application/pdf")},
            )
        print(f"[UPLOAD] HTTP {r.status_code}")
        if r.status_code == 409:
            # Duplicate - try to find and use existing doc
            print(f"[UPLOAD] Duplicate: {r.json().get('error',{}).get('details',{})}")
            DOC_ID = r.json().get("error", {}).get("details", {}).get("existing_document_id")
            if DOC_ID:
                print(f"[UPLOAD] Using existing document: {DOC_ID}")
                return True
            return False
        elif r.status_code != 201:
            print(f"[UPLOAD] Failed: {r.text}")
            return False
        
        data = r.json()
        DOC_ID = data["document"]["id"]
        print(f"[UPLOAD] Document: {DOC_ID}, Status: {data['document']['status']}")
        print(f"[UPLOAD] Job: {data['job']['job_id']}, Status: {data['job']['status']}")
        return True


async def run_ingestion():
    """Run ingestion pipeline inside Docker container."""
    import subprocess
    cmd = (
        f'docker compose exec -u root api python -c "'
        f'import asyncio; '
        f'from app.db.session import async_session_factory; '
        f'from app.storage.factory import get_storage_provider; '
        f'from app.ingestion.pipeline import IngestionPipeline; '
        f'from app.ingestion.repository import DocumentRepository; '
        f'async def run(): '
        f'    async with async_session_factory() as db: '
        f'        storage = await get_storage_provider(); '
        f'        doc_repo = DocumentRepository(db); '
        f'        doc = await doc_repo.get_by_id(\"{DOC_ID}\"); '
        f'        print(f\"Doc: {{doc.original_filename}} ({{doc.mime_type}})\"); '
        f'        pipeline = IngestionPipeline(db, storage); '
        f'        stats = await pipeline.run('
        f'            document_id=\"{DOC_ID}\", '
        f'            file_path=f\"documents/{DOC_ID}\", '
        f'            mime_type=doc.mime_type, '
        f'            user_id=doc.user_id or \"system\"); '
        f'        print(f\"OK: chunks={{stats.get(chr(34)+\"chunk_count\"+chr(34))}} pages={{stats.get(chr(34)+\"page_count\"+chr(34))}} lang={{stats.get(chr(34)+\"language\"+chr(34))}}\"); '
        f'asyncio.run(run())"'
    )
    # Use raw string to avoid bash escaping issues
    direct = (
        f'docker compose exec -u root api python -c "'
        f'import asyncio; '
        f'from app.db.session import async_session_factory; '
        f'from app.storage.factory import get_storage_provider; '
        f'from app.ingestion.pipeline import IngestionPipeline; '
        f'from app.ingestion.repository import DocumentRepository; '
        f'async def r(): '
        f'  async with async_session_factory() as db: '
        f'    storage=await get_storage_provider(); '
        f'    rr=DocumentRepository(db); '
        f'    d=await rr.get_by_id(\"{DOC_ID}\"); '
        f'    p=IngestionPipeline(db,storage); '
        f'    s=await p.run(document_id=\"{DOC_ID}\",file_path=f\"documents/{DOC_ID}\",mime_type=d.mime_type,user_id=d.user_id or \"s\"); '
        f'    print(json.dumps(s)); '
        f'import json; '
        f'asyncio.run(r())"'
    )
    proc = await asyncio.create_subprocess_shell(
        direct, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    result = stdout.decode() + stderr.decode()
    print(f"[INGESTION] {result[:500]}")
    return "Traceback" not in result and proc.returncode == 0


async def start_indexing():
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/indexing/start",
            params={"document_id": DOC_ID, "collection_name": "documents", "use_arq": "false"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        print(f"[INDEXING START] HTTP {r.status_code}")
        if r.status_code != 200:
            print(f"[INDEXING START] Failed: {r.text}")
            return False
        print(f"[INDEXING START] {r.json()}")
        
        # Poll for completion
        for i in range(15):
            await asyncio.sleep(5)
            sr = await client.get(
                f"{API}/documents/{DOC_ID}/status",
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
            if sr.status_code != 200:
                continue
            status = sr.json().get("status", "?")
            progress = sr.json().get("progress", "?")
            print(f"  Poll {i+1}: status={status}, progress={progress}")
            if status in ("completed", "failed"):
                if status == "completed":
                    # Get doc stats
                    dr = await client.get(
                        f"{API}/documents/{DOC_ID}",
                        headers={"Authorization": f"Bearer {TOKEN}"},
                    )
                    if dr.status_code == 200:
                        d = dr.json()
                        print(f"[INDEXING] Chunks: {d.get('chunk_count')}, Pages: {d.get('page_count')}")
                return status == "completed"
        return False


async def test_retrieval():
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/retrieval/search",
            json={
                "query": "What embedding model does the platform use?",
                "collection_name": "documents",
                "method": "hybrid",
                "top_k": 5,
                "rerank": False,
            },
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        print(f"[RETRIEVAL] HTTP {r.status_code}")
        if r.status_code != 200:
            print(f"[RETRIEVAL] Failed: {r.text}")
            return False
        data = r.json()
        chunks = data.get("chunks", [])
        print(f"[RETRIEVAL] Retrieved {len(chunks)} chunks")
        for c in chunks[:3]:
            print(f"  Score: {c.get('score',0):.3f}, Doc: {c.get('document_id','?')[:8]}..., Text: {c.get('text','')[:80]}...")
        return len(chunks) > 0


async def test_rag():
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/chat",
            json={
                "question": "What embedding model does the Enterprise RAG platform use and what is its vector dimension?",
                "collection_name": "documents",
                "retrieval_method": "hybrid",
                "top_k": 5,
                "rerank": False,
                "query_rewrite": False,
            },
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        print(f"[RAG] HTTP {r.status_code}")
        if r.status_code != 200:
            print(f"[RAG] Failed: {r.text[:500]}")
            return False
        data = r.json()
        print(f"[RAG] Answer: {data.get('answer','')[:200]}...")
        citations = data.get("citations", [])
        print(f"[RAG] Citations: {len(citations)}")
        for c in citations[:3]:
            print(f"  Doc: {c.get('document_id','?')[:8]}..., Page: {c.get('page_number','?')}")
        print(f"[RAG] Grounding valid: {data.get('grounding_valid','?')}")
        print(f"[RAG] Duration: {data.get('total_duration_ms',0)}ms")
        return bool(data.get("answer"))


async def test_deletion():
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{API}/documents/{DOC_ID}",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        print(f"[DELETION] HTTP {r.status_code}")
        print(f"[DELETION] {r.text}")
        return r.status_code == 200


async def main():
    print("=" * 60)
    print("COMPLETE RAG PIPELINE VERIFICATION")
    print("=" * 60)
    
    # Login
    await login()
    
    # Upload
    if not await upload():
        print("[FAIL] Upload stage failed")
        return
    
    # Ingestion
    if not await run_ingestion():
        print("[FAIL] Ingestion stage failed")
        return
    
    # Check doc status after ingestion
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{API}/documents/{DOC_ID}", headers={"Authorization": f"Bearer {TOKEN}"})
        if r.status_code == 200:
            d = r.json()
            print(f"[DOC STATUS] Chunks: {d.get('chunk_count')}, Pages: {d.get('page_count')}")
    
    # Start indexing
    if not await start_indexing():
        print("[FAIL] Indexing stage failed")
        return
    
    # Test retrieval
    if not await test_retrieval():
        print("[FAIL] Retrieval stage failed")
        return
    
    # Test RAG
    if not await test_rag():
        print("[FAIL] RAG stage failed")
        return
    
    # Test deletion
    if not await test_deletion():
        print("[FAIL] Deletion stage failed")
        return
    
    print()
    print("=" * 60)
    print("ALL PIPELINE STAGES COMPLETED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
