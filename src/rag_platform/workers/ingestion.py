from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from rag_platform.application.db.models import (
    Document,
    DocumentPermission,
    DocumentVersion,
    IngestionEvent,
    IngestionJob,
)
from rag_platform.application.db.session import Database
from rag_platform.config import Settings, load_settings

logger = logging.getLogger("rag_platform.ingestion_worker")


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    page_count: int
    chunk_count: int
    parser_version: str
    chunker_version: str
    embedding_version: str


class DocumentProcessor(Protocol):
    async def process(
        self, job: IngestionJob, document: Document, version: DocumentVersion
    ) -> ProcessingResult: ...

    async def delete(
        self, job: IngestionJob, document: Document, version: DocumentVersion
    ) -> None: ...


class UnconfiguredProcessor:
    async def process(self, job, document, version) -> ProcessingResult:
        raise RuntimeError(
            "No production document processor is configured. Inject an S3/parser/index adapter."
        )

    async def delete(self, job, document, version) -> None:
        raise RuntimeError("No production deletion processor is configured.")


class IngestionWorker:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        processor: DocumentProcessor,
        *,
        worker_id: str | None = None,
    ):
        self.settings = settings
        self.database = database
        self.processor = processor
        self.worker_id = worker_id or f"ingestion-{socket.gethostname()}"

    async def claim(self, session: AsyncSession) -> list[str]:
        jobs = list(
            (
                await session.scalars(
                    select(IngestionJob)
                    .where(
                        IngestionJob.status == "QUEUED",
                        IngestionJob.attempts < self.settings.worker.max_attempts,
                    )
                    .order_by(IngestionJob.created_at)
                    .limit(self.settings.worker.batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        now = datetime.now(UTC)
        for job in jobs:
            job.status = "RUNNING"
            job.worker_id = self.worker_id
            job.attempts += 1
            job.started_at = job.started_at or now
            session.add(
                IngestionEvent(
                    tenant_id=job.tenant_id,
                    job_id=job.id,
                    stage=job.stage,
                    status="RUNNING",
                    progress_percent=job.progress_percent,
                    message=f"Claimed by {self.worker_id}",
                )
            )
        await session.commit()
        return [job.id for job in jobs]

    async def process_job(self, job_id: str) -> None:
        async with self.database.sessions() as session:
            job = await session.get(IngestionJob, job_id)
            if job is None or job.status != "RUNNING":
                return
            document = await session.get(Document, job.document_id)
            version = await session.get(DocumentVersion, job.document_version_id)
            if document is None or version is None:
                await self._fail(session, job, "MISSING_RECORD", "Document or version is missing")
                return
            try:
                if job.job_type == "DELETE":
                    await self.processor.delete(job, document, version)
                    await session.execute(
                        delete(DocumentPermission).where(
                            DocumentPermission.document_id == document.id
                        )
                    )
                    document.status = "DELETED"
                    version.status = "DELETED"
                else:
                    result = await self.processor.process(job, document, version)
                    await self._activate_version(session, job, document, version, result)
                job.status = "SUCCEEDED"
                job.stage = "ACTIVE" if job.job_type != "DELETE" else "DELETED"
                job.progress_percent = 100
                job.completed_at = datetime.now(UTC)
                session.add(
                    IngestionEvent(
                        tenant_id=job.tenant_id,
                        job_id=job.id,
                        stage=job.stage,
                        status="SUCCEEDED",
                        progress_percent=100,
                    )
                )
                await session.commit()
            except Exception as exc:
                await self._fail(session, job, "PROCESSING_FAILED", str(exc))

    async def _activate_version(
        self,
        session: AsyncSession,
        job: IngestionJob,
        document: Document,
        version: DocumentVersion,
        result: ProcessingResult,
    ) -> None:
        """Switch only after the replacement has fully parsed, indexed, and validated."""
        old_version_id = document.current_version_id
        version.page_count = result.page_count
        version.chunk_count = result.chunk_count
        version.parser_version = result.parser_version
        version.chunker_version = result.chunker_version
        version.embedding_version = result.embedding_version
        version.status = "ACTIVE"
        version.active_at = datetime.now(UTC)
        document.current_version_id = version.id
        document.status = "ACTIVE"
        if old_version_id and old_version_id != version.id:
            old = await session.get(DocumentVersion, old_version_id)
            if old:
                old.status = "INACTIVE"
                old.deactivated_at = datetime.now(UTC)

    async def _fail(
        self, session: AsyncSession, job: IngestionJob, code: str, message: str
    ) -> None:
        job.status = "FAILED"
        job.error_code = code
        job.error_message = message[:4000]
        job.completed_at = datetime.now(UTC)
        version = await session.get(DocumentVersion, job.document_version_id)
        document = await session.get(Document, job.document_id)
        if version and job.job_type != "DELETE":
            version.status = "FAILED"
        # Preserve the old working document/version when a replacement fails.
        if document and document.current_version_id is None:
            document.status = "FAILED_INGESTION"
        session.add(
            IngestionEvent(
                tenant_id=job.tenant_id,
                job_id=job.id,
                stage=job.stage,
                status="FAILED",
                progress_percent=job.progress_percent,
                message=job.error_message,
                details={"error_code": code},
            )
        )
        await session.commit()

    async def run_once(self) -> int:
        async with self.database.sessions() as session:
            job_ids = await self.claim(session)
        for job_id in job_ids:
            await self.process_job(job_id)
        return len(job_ids)

    async def run_forever(self) -> None:
        while True:
            count = await self.run_once()
            if count == 0:
                await asyncio.sleep(self.settings.worker.poll_interval_seconds)


async def _main() -> None:
    settings = load_settings()
    database = Database(settings.database)
    try:
        await IngestionWorker(settings, database, UnconfiguredProcessor()).run_forever()
    finally:
        await database.dispose()


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
