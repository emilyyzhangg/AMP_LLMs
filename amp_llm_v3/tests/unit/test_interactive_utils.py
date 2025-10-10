# tests/test_interactive_utils.py
import asyncio
import io
import tempfile
from pathlib import Path
import pytest
import monkeypatch

from amp_llm.llm.utils import interactive as iu


@pytest.mark.asyncio
async def test_handle_paste_command(monkeypatch):
    """Simulate paste mode input."""
    inputs = iter(["line 1", "line 2", "<<<end"])
    captured = []

    async def fake_input(prompt=""):
        return next(inputs)

    async def fake_print(*args, **kwargs):
        captured.append(" ".join(str(a) for a in args))

    result = await iu.handle_paste_command(fake_input, fake_print)
    assert "line 1" in result
    assert "line 2" in result
    assert "Paste mode" in captured[0]


@pytest.mark.asyncio
async def test_handle_load_command_file_only(tmp_path):
    """Load content from a file."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("Hello World")

    async def fake_input(prompt=""):
        return ""

    async def fake_print(*args, **kwargs):
        pass

    result = await iu.handle_load_command(f"load {file_path}", fake_input, fake_print, logger=None)
    assert "Hello World" in result
    assert "Content of" in result or "content" in result.lower()


@pytest.mark.asyncio
async def test_handle_load_command_with_question(tmp_path):
    """Load file and ask question."""
    file_path = tmp_path / "notes.txt"
    file_path.write_text("Some technical content")

    async def fake_input(prompt=""):
        return ""

    async def fake_print(*args, **kwargs):
        pass

    result = await iu.handle_load_command(
        f"load {file_path} what is this?",
        fake_input,
        fake_print,
        logger=None
    )
    assert "technical content" in result
    assert "what is this?" in result.lower()


@pytest.mark.asyncio
async def test_list_output_files(tmp_path):
    """Ensure list_output_files prints all files in output/."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "file1.txt").write_text("a")
    (output_dir / "file2.txt").write_text("b")

    captured = []

    async def fake_print(*args, **kwargs):
        captured.append(" ".join(str(a) for a in args))

    # Patch Path.cwd to use tmp_path as base directory
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

    await iu.list_output_files(fake_print)
    assert any("file1.txt" in line for line in captured)
    assert any("file2.txt" in line for line in captured)


@pytest.mark.asyncio
async def test_show_pwd(monkeypatch):
    """Ensure show_pwd prints current directory."""
    captured = []

    async def fake_print(*args, **kwargs):
        captured.append(" ".join(str(a) for a in args))

    monkeypatch.setattr(Path, "cwd", lambda: Path("/mock/path"))

    await iu.show_pwd(fake_print)
    assert any("/mock/path" in line for line in captured)
