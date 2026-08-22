from pathlib import Path

from typer.testing import CliRunner

from rag_platform.cli import app

runner = CliRunner()


def test_cli_ingest_inspect_and_chunks(text_pdf: Path, tmp_path: Path) -> None:
    data_dir = tmp_path / "cli-data"
    result = runner.invoke(
        app,
        ["ingest", str(text_pdf), "--data-dir", str(data_dir), "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = __import__("json").loads(result.stdout)
    document_id = payload["document"]["document_id"]

    inspected = runner.invoke(
        app,
        ["inspect", document_id, "--data-dir", str(data_dir), "--json"],
    )
    assert inspected.exit_code == 0, inspected.output
    assert document_id in inspected.stdout

    chunks = runner.invoke(
        app,
        ["chunks", document_id, "--data-dir", str(data_dir), "--json"],
    )
    assert chunks.exit_code == 0, chunks.output
    assert "chunk_id" in chunks.stdout
