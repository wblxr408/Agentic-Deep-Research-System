"""
Document source CRUD and ingest API.
"""

from __future__ import annotations

import io
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.db.connection import Document, DocumentSource, get_db_pool
from app.rag.embedder import Embedder

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {"json", "md", "docx", "pdf", "txt"}


class DocumentSourceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    group_name: str = Field(min_length=1, max_length=100)
    source_type: str = Field(default="manual", max_length=20)
    content: str | None = None
    file_name: str | None = None
    file_ext: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunk_size: int = Field(default=400, ge=100, le=4000)
    chunk_overlap: int = Field(default=80, ge=0, le=1000)


class DocumentSourceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    group_name: str | None = Field(default=None, min_length=1, max_length=100)
    metadata: dict[str, Any] | None = None
    status: str | None = Field(default=None, max_length=20)


def _slug_group(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]+", "_", name.strip()).strip("_").lower() or "default"


def _chunk_text(text: str, chunk_size: int = 400, overlap: int = 80) -> list[str]:
    text = re.sub(r"\r\n?", "\n", text).strip()
    if not text:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    def flush_current() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            flush_current()
            start = 0
            while start < len(paragraph):
                end = min(start + chunk_size, len(paragraph))
                chunks.append(paragraph[start:end].strip())
                if end >= len(paragraph):
                    break
                start = max(end - overlap, start + 1)
            continue

        if not current:
            current = paragraph
            continue

        if len(current) + len(paragraph) + 2 <= chunk_size:
            current = current + "\n\n" + paragraph
        else:
            flush_current()
            current = paragraph

    flush_current()
    return chunks


def _extract_text_from_json(data: Any) -> str:
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        return "\n".join(_extract_text_from_json(item) for item in data)
    if isinstance(data, dict):
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                nested = _extract_text_from_json(value)
                if nested:
                    lines.append(f"{key}: {nested}")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)
    return str(data)


def _extract_plain_text(file_name: str, file_ext: str, raw: bytes) -> str:
    ext = file_ext.lower()
    if ext in {"txt", "md"}:
        return raw.decode("utf-8", errors="ignore")
    if ext == "json":
        data = json.loads(raw.decode("utf-8", errors="ignore"))
        return _extract_text_from_json(data)
    if ext == "docx":
        try:
            import docx  # type: ignore
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"docx_support_missing:{exc}")
        document = docx.Document(io.BytesIO(raw))
        return "\n".join(p.text for p in document.paragraphs)
    if ext == "pdf":
        try:
            from pypdf import PdfReader  # type: ignore
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"pdf_support_missing:{exc}")
        reader = PdfReader(io.BytesIO(raw))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    raise HTTPException(status_code=400, detail=f"unsupported_file_type:{file_name}")


async def _ingest_source(
    *,
    name: str,
    group_name: str,
    source_type: str,
    content: str,
    metadata: dict[str, Any],
    file_name: str | None = None,
    file_ext: str | None = None,
    chunk_size: int = 400,
    chunk_overlap: int = 80,
) -> dict[str, Any]:
    text = content.strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty_content")

    source_id = await DocumentSource.create(
        name=name,
        group_name=group_name,
        source_type=source_type,
        file_name=file_name,
        file_ext=file_ext,
        original_text=text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        metadata=metadata,
    )

    chunks = _chunk_text(text, chunk_size=chunk_size, overlap=chunk_overlap)
    embedder = Embedder()
    embeddings = await embedder.embed_batch(chunks) if chunks else []

    created_doc_ids: list[str] = []
    for index, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=False)):
        chunk_metadata = {
            **metadata,
            "group": group_name,
            "source_name": name,
            "source_type": source_type,
            "file_name": file_name,
            "file_ext": file_ext,
            "chunk_index": index,
            "chunk_count": len(chunks),
        }
        doc_id = await Document.create(
            content=chunk,
            metadata=chunk_metadata,
            embedding=embedding,
            source_id=source_id,
            source_name=name,
            source_type=source_type,
            chunk_index=index,
            chunk_count=len(chunks),
        )
        created_doc_ids.append(doc_id)

    return {
        "source_id": source_id,
        "chunk_count": len(created_doc_ids),
        "document_ids": created_doc_ids,
    }


@router.get("/sources")
async def list_sources(group_name: str | None = None):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if group_name:
            rows = await conn.fetch(
                """
                SELECT id, name, group_name, source_type, file_name, file_ext, status,
                       original_text, chunk_size, chunk_overlap, metadata,
                       created_at, updated_at
                FROM document_sources
                WHERE group_name = $1
                ORDER BY created_at DESC
                """,
                group_name,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, name, group_name, source_type, file_name, file_ext, status,
                       original_text, chunk_size, chunk_overlap, metadata,
                       created_at, updated_at
                FROM document_sources
                ORDER BY created_at DESC
                """
            )
    return {"items": [dict(row) for row in rows]}


@router.post("/sources")
async def create_source(payload: DocumentSourceCreateRequest):
    content = payload.content or ""
    result = await _ingest_source(
        name=payload.name,
        group_name=payload.group_name,
        source_type=payload.source_type,
        content=content,
        metadata=payload.metadata,
        file_name=payload.file_name,
        file_ext=payload.file_ext,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
    )
    return result


@router.put("/sources/{source_id}")
async def update_source(source_id: str, payload: DocumentSourceUpdateRequest):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM document_sources WHERE id = $1::uuid",
            source_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="source_not_found")

        next_name = payload.name or row["name"]
        next_group = payload.group_name or row["group_name"]
        next_metadata = payload.metadata if payload.metadata is not None else row["metadata"]
        next_status = payload.status or row["status"]
        await conn.execute(
            """
            UPDATE document_sources
            SET name = $2, group_name = $3, metadata = $4::jsonb, status = $5, updated_at = $6
            WHERE id = $1::uuid
            """,
            source_id,
            next_name,
            next_group,
            json.dumps(next_metadata, ensure_ascii=False),
            next_status,
            datetime.utcnow(),
        )

    return {"source_id": source_id, "name": next_name, "group_name": next_group}


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM documents WHERE source_id = $1::uuid", source_id)
        await conn.execute("DELETE FROM document_sources WHERE id = $1::uuid", source_id)
    return {"source_id": source_id, "deleted": True}


@router.post("/upload")
async def upload_source(
    file: UploadFile = File(...),
    name: str = Form(...),
    group_name: str = Form(...),
    source_type: str = Form(default="upload"),
    chunk_size: int = Form(default=400),
    chunk_overlap: int = Form(default=80),
):
    suffix = Path(file.filename or "").suffix.lower().lstrip(".")
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"unsupported_file_type:{suffix}")

    raw = await file.read()
    content = _extract_plain_text(file.filename or name, suffix, raw)
    return await _ingest_source(
        name=name,
        group_name=group_name,
        source_type=source_type,
        content=content,
        metadata={"uploaded_file": file.filename},
        file_name=file.filename,
        file_ext=suffix,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


@router.get("/chunks")
async def list_chunks(source_id: str | None = None, group_name: str | None = None):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if source_id:
            rows = await conn.fetch(
                """
                SELECT id, source_id, source_name, source_type, chunk_index, chunk_count,
                       content, metadata, created_at, updated_at
                FROM documents
                WHERE source_id = $1::uuid
                ORDER BY chunk_index ASC
                """,
                source_id,
            )
        elif group_name:
            rows = await conn.fetch(
                """
                SELECT d.id, d.source_id, d.source_name, d.source_type, d.chunk_index, d.chunk_count,
                       d.content, d.metadata, d.created_at, d.updated_at
                FROM documents d
                LEFT JOIN document_sources s ON s.id = d.source_id
                WHERE s.group_name = $1 OR d.metadata->>'group' = $1
                ORDER BY d.created_at DESC, d.chunk_index ASC
                """,
                group_name,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, source_id, source_name, source_type, chunk_index, chunk_count,
                       content, metadata, created_at, updated_at
                FROM documents
                ORDER BY created_at DESC
                LIMIT 200
                """
            )
    return {"items": [dict(row) for row in rows]}
