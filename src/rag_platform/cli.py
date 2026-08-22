from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from rag_platform.config import Settings
from rag_platform.domain.states import IssueSeverity
from rag_platform.ingestion.service import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    IngestionRejected,
    IngestionService,
)

app = typer.Typer(
    name="ragctl",
    help="Developer CLI for Phase 0/1 document ingestion and inspection.",
    no_args_is_help=True,
)
console = Console()


def _service(data_dir: Path) -> IngestionService:
    return IngestionService(Settings(data_dir=data_dir))


def _issue_table(issues: list[object]) -> Table:
    table = Table(title="Validation issues")
    table.add_column("Severity")
    table.add_column("Code")
    table.add_column("Message")
    for issue in issues:
        table.add_row(issue.severity.value, issue.code.value, issue.message)
    return table


@app.command()
def validate(
    path: Annotated[Path, typer.Argument(exists=False, dir_okay=False)],
    data_dir: Annotated[Path, typer.Option("--data-dir")] = Path(".rag_data"),
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate a PDF without adding it to the local catalog."""
    service = _service(data_dir)
    issues, details = service.validate(path.expanduser().resolve())
    payload = {
        "path": str(path),
        "valid": not any(issue.severity == IssueSeverity.ERROR for issue in issues),
        "details": details,
        "issues": [issue.model_dump(mode="json") for issue in issues],
    }
    if json_output:
        console.print_json(json.dumps(payload))
    else:
        console.print(f"[bold]File:[/bold] {path}")
        console.print(f"[bold]Valid:[/bold] {payload['valid']}")
        console.print(f"[bold]Pages:[/bold] {details.get('page_count', 0)}")
        console.print(f"[bold]SHA256:[/bold] {details.get('checksum_sha256') or '-'}")
        if issues:
            console.print(_issue_table(issues))
    if not payload["valid"]:
        raise typer.Exit(2)


@app.command()
def ingest(
    path: Annotated[Path, typer.Argument(exists=False, dir_okay=False)],
    source: Annotated[str, typer.Option("--source")] = "manual",
    document_version: Annotated[int, typer.Option("--document-version", min=1)] = 1,
    chunk_size: Annotated[int | None, typer.Option("--chunk-size", min=100)] = None,
    chunk_overlap: Annotated[int | None, typer.Option("--chunk-overlap", min=0)] = None,
    data_dir: Annotated[Path, typer.Option("--data-dir")] = Path(".rag_data"),
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate, extract, clean, chunk, and persist one PDF."""
    service = _service(data_dir)
    try:
        result = service.ingest(
            path,
            source=source,
            document_version=document_version,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    except DuplicateDocumentError as exc:
        console.print(f"[yellow]Duplicate:[/yellow] already stored as {exc.existing_document_id}")
        raise typer.Exit(3) from exc
    except IngestionRejected as exc:
        console.print(f"[red]Rejected[/red] document_id={exc.document_id or '-'}")
        if exc.issues:
            console.print(_issue_table(exc.issues))
        raise typer.Exit(2) from exc

    payload = {
        "document": result.document.model_dump(mode="json"),
        "chunk_count": result.chunk_count,
        "stored_path": str(result.stored_path),
        "issues": [issue.model_dump(mode="json") for issue in result.issues],
    }
    if json_output:
        console.print_json(json.dumps(payload))
        return

    console.print("[green bold]Ingestion complete[/green bold]")
    console.print(f"Document ID: {result.document.document_id}")
    console.print(f"Status:      {result.document.status.value}")
    console.print(f"Pages:       {result.document.page_count}")
    console.print(f"Chunks:      {result.chunk_count}")
    console.print(f"SHA256:      {result.document.checksum_sha256}")
    console.print(f"Stored copy: {result.stored_path}")
    if result.issues:
        console.print(_issue_table(result.issues))


@app.command("ingest-dir")
def ingest_dir(
    directory: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
    source: Annotated[str, typer.Option("--source")] = "manual",
    data_dir: Annotated[Path, typer.Option("--data-dir")] = Path(".rag_data"),
) -> None:
    """Recursively ingest PDFs from a directory; useful for the 10 -> 20 -> 50 corpus rollout."""
    service = _service(data_dir)
    pdfs = sorted(directory.rglob("*.pdf"))
    if limit is not None:
        pdfs = pdfs[:limit]
    if not pdfs:
        console.print("[yellow]No PDFs found.[/yellow]")
        return

    table = Table(title=f"Batch ingestion: {len(pdfs)} PDF(s)")
    table.add_column("File")
    table.add_column("Result")
    table.add_column("Document ID")
    table.add_column("Chunks", justify="right")
    failures = 0

    for path in pdfs:
        try:
            result = service.ingest(path, source=source)
            table.add_row(path.name, "ACTIVE", result.document.document_id, str(result.chunk_count))
        except DuplicateDocumentError as exc:
            table.add_row(path.name, "DUPLICATE", exc.existing_document_id, "-")
        except IngestionRejected as exc:
            failures += 1
            codes = ",".join(
                issue.code.value for issue in exc.issues if issue.severity == IssueSeverity.ERROR
            )
            table.add_row(path.name, f"REJECTED:{codes}", exc.document_id or "-", "-")

    console.print(table)
    if failures:
        raise typer.Exit(2)


@app.command("list")
def list_documents(
    data_dir: Annotated[Path, typer.Option("--data-dir")] = Path(".rag_data"),
    include_deleted: Annotated[bool, typer.Option("--all")] = False,
) -> None:
    """List documents in the local Phase 1 catalog."""
    documents = _service(data_dir).catalog.list_documents(include_deleted=include_deleted)
    table = Table(title="Documents")
    table.add_column("Document ID")
    table.add_column("Status")
    table.add_column("Pages", justify="right")
    table.add_column("Filename")
    table.add_column("Source")
    for document in documents:
        table.add_row(
            document.document_id,
            document.status.value,
            str(document.page_count),
            document.filename,
            document.source,
        )
    console.print(table)


@app.command()
def inspect(
    document_id: Annotated[str, typer.Argument()],
    data_dir: Annotated[Path, typer.Option("--data-dir")] = Path(".rag_data"),
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Inspect persisted document metadata, status, issues, and chunk count."""
    service = _service(data_dir)
    try:
        document, issues, chunk_count, stored_path = service.inspect(document_id)
    except DocumentNotFoundError as exc:
        console.print(f"[red]Document not found:[/red] {document_id}")
        raise typer.Exit(4) from exc

    payload = {
        "document": document.model_dump(mode="json"),
        "chunk_count": chunk_count,
        "stored_path": stored_path,
        "issues": [issue.model_dump(mode="json") for issue in issues],
    }
    if json_output:
        console.print_json(json.dumps(payload))
        return

    table = Table(title=document_id, show_header=False)
    for key, value in payload["document"].items():
        table.add_row(key, str(value))
    table.add_row("chunk_count", str(chunk_count))
    table.add_row("stored_path", stored_path or "-")
    console.print(table)
    if issues:
        console.print(_issue_table(issues))


@app.command()
def chunks(
    document_id: Annotated[str, typer.Argument()],
    page: Annotated[int | None, typer.Option("--page", min=1)] = None,
    limit: Annotated[int, typer.Option("--limit", min=1)] = 20,
    full: Annotated[bool, typer.Option("--full")] = False,
    data_dir: Annotated[Path, typer.Option("--data-dir")] = Path(".rag_data"),
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show chunks for an ingested document."""
    service = _service(data_dir)
    if not service.catalog.get_document(document_id):
        console.print(f"[red]Document not found:[/red] {document_id}")
        raise typer.Exit(4)
    records = service.catalog.get_chunks(document_id, page=page, limit=limit)
    if json_output:
        console.print_json(json.dumps([record.model_dump(mode="json") for record in records]))
        return

    table = Table(title=f"Chunks: {document_id}")
    table.add_column("#", justify="right")
    table.add_column("Page", justify="right")
    table.add_column("Chars")
    table.add_column("Text")
    for chunk in records:
        text = chunk.text if full else (chunk.text[:180] + ("..." if len(chunk.text) > 180 else ""))
        table.add_row(
            str(chunk.chunk_index), str(chunk.page), f"{chunk.char_start}:{chunk.char_end}", text
        )
    console.print(table)


@app.command()
def delete(
    document_id: Annotated[str, typer.Argument()],
    keep_file: Annotated[bool, typer.Option("--keep-file")] = False,
    data_dir: Annotated[Path, typer.Option("--data-dir")] = Path(".rag_data"),
) -> None:
    """Soft-delete document metadata and remove chunks; purge the stored PDF by default."""
    service = _service(data_dir)
    try:
        document = service.delete(document_id, purge_file=not keep_file)
    except DocumentNotFoundError as exc:
        console.print(f"[red]Document not found:[/red] {document_id}")
        raise typer.Exit(4) from exc
    console.print(f"[green]Deleted[/green] {document.document_id} -> {document.status.value}")


if __name__ == "__main__":
    app()
