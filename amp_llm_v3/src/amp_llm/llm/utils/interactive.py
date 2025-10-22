# src/amp_llm/llm/utils/interactive_utils.py
"""
Interactive helpers for LLM runners: paste mode, file loading/searching,
directory listing, and simple utilities.

All functions are async and built to be imported by runners (API or SSH).
They expect an `ainput` and `aprint` asynchronous interface (aioconsole or fallbacks).
"""
from pathlib import Path
from typing import Optional, Tuple, Callable, List, Awaitable
import logging
import os

logger = logging.getLogger(__name__)

# Type aliases for async I/O functions
AInput = Callable[[str], Awaitable[str]]
APrint = Callable[..., Awaitable[None]]


async def handle_paste_command(ainput: AInput, aprint: APrint) -> Optional[str]:
    """
    Multi-line paste mode. User ends input with a line containing <<<end (case insensitive).
    Returns the concatenated pasted text or None if cancelled / empty.
    """
    await aprint("\n📋 Multi-line paste mode activated")
    await aprint("Instructions: paste your content, then type '<<<end' on a new line to finish\n")

    lines: List[str] = []
    while True:
        try:
            line = await ainput("")
        except KeyboardInterrupt:
            await aprint("❌ Paste mode cancelled")
            return None
        if line.strip().lower() == "<<<end":
            break
        lines.append(line)

    if not lines:
        await aprint("❌ No content captured.")
        return None

    text = "\n".join(lines).rstrip()
    await aprint(f"✅ Captured {len(lines)} lines ({len(text)} characters)")
    return text


def _search_candidates(filename: str) -> List[Path]:
    """Return a list of candidate Paths (not filtered for existence)."""
    p = Path(filename)
    candidates = [
        p,
        Path("output") / filename,
        Path("output") / f"{filename}.txt",
        Path("output") / f"{filename}.json",
        Path(filename + ".txt"),
        Path(filename + ".json"),
        Path(".") / filename,
        Path("..") / filename,
        Path("..") / "output" / filename,
    ]
    # deduplicate while preserving order
    seen = set()
    out = []
    for c in candidates:
        try:
            key = str(c.resolve())
        except Exception:
            key = str(c)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _read_file_with_fallback(path: Path) -> str:
    """Read file with utf-8 first, then latin-1 fallback. Raises if not readable."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


async def handle_load_command(
    raw_prompt: str,
    ainput: AInput,
    aprint: APrint,
    logger: Optional[logging.Logger] = None
) -> Optional[str]:
    """
    Handle 'load <filename> [optional question]' commands.

    Returns:
        str: final prompt to send to model (file content + question), or None if cancelled.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    # parse: raw_prompt starts with "load "
    rest = raw_prompt[5:].strip()
    if not rest:
        await aprint("❌ Usage: load <filename> [optional question]")
        return None

    parts = rest.split(maxsplit=1)
    filename = parts[0]
    optional_question = parts[1] if len(parts) > 1 else None

    await aprint(f"🔍 Searching for: {filename}")
    candidates = _search_candidates(filename)

    found_path: Optional[Path] = None
    for c in candidates:
        try:
            if c.exists() and c.is_file():
                found_path = c
                await aprint(f"✓ Found at: {c.resolve()}")
                break
        except Exception as e:
            logger.debug(f"Error checking candidate {c}: {e}")

    if not found_path:
        await aprint(f"❌ File not found: {filename}")
        await aprint(f"📂 Current working directory: {Path.cwd().absolute()}")
        await aprint("\nSearched paths:")
        for c in candidates:
            try:
                exists = "✓ EXISTS" if c.exists() and c.is_file() else "✗ not found"
            except Exception:
                exists = "✗ invalid"
            await aprint(f"  • {c} [{exists}]")
        # show output directory preview if present
        out_dir = Path("output")
        if out_dir.exists() and out_dir.is_dir():
            try:
                files = sorted(list(out_dir.iterdir()))
                if files:
                    await aprint("\n📁 Files in output/:")
                    for f in files[:20]:
                        await aprint(f"  • {f.name}")
                    if len(files) > 20:
                        await aprint(f"  ... and {len(files)-20} more")
            except Exception as e:
                logger.debug(f"Error listing output/: {e}")
        return None

    # read file
    try:
        file_content = _read_file_with_fallback(found_path)
    except Exception as e:
        await aprint(f"❌ Error reading file: {e}")
        logger.error(f"Error reading {found_path}: {e}", exc_info=True)
        return None

    await aprint(f"✅ Loaded {found_path.name} ({len(file_content)} chars)")
    preview = file_content[:200]
    if len(file_content) > 200:
        preview += "..."
    await aprint(f"Preview:\n{preview}\n")

    # get question / context
    if optional_question:
        question = optional_question
        await aprint(f"Question passed inline: {question}")
    else:
        question = await ainput("Add a question/instruction (or press Enter to analyze file): ")
        question = question.strip()

    if question:
        final_prompt = f"{question}\n\n```\n{file_content}\n```"
    else:
        final_prompt = f"Please analyze this content:\n\n```\n{file_content}\n```"

    return final_prompt


async def list_output_files(aprint: APrint) -> None:
    """List files in the 'output' directory (preview)."""
    out = Path("output")
    await aprint(f"📂 Current directory: {Path.cwd().absolute()}")
    if out.exists() and out.is_dir():
        try:
            files = sorted(list(out.iterdir()))
            if not files:
                await aprint("⚠️ output/ directory exists but is empty")
                return
            await aprint("\n📁 Files in output/:")
            for f in files[:50]:
                size = f.stat().st_size if f.is_file() else 0
                kind = "📄" if f.is_file() else "📁"
                await aprint(f"  {kind} {f.name} ({size:,} bytes)")
            if len(files) > 50:
                await aprint(f"  ... and {len(files)-50} more")
        except Exception as e:
            await aprint(f"Error listing output/: {e}")
    else:
        await aprint("⚠️ output/ directory does not exist")


async def show_pwd(aprint: APrint) -> None:
    """Print current working directory."""
    await aprint(f"📂 Current working directory: {Path.cwd().absolute()}")
