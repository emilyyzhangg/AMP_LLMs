"""
LLM utility functions for Ollama interaction.
Includes both SSH terminal and HTTP API methods.
FIXED: Better connection management, keepalive, and retry logic
"""
import asyncio
import aiohttp
import json
import shlex
import re
from typing import Optional
from config import get_config, get_logger

logger = get_logger(__name__)
config = get_config()

# ANSI escape sequence pattern
ANSI_ESCAPE = re.compile(r'(?:\x1B[@-_][0-?]*[ -/]*[@-~])')


def clean(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return ANSI_ESCAPE.sub('', text).strip()


# ============================================================================
# HTTP API METHODS (RECOMMENDED - No fragmentation issues)
# ============================================================================

async def list_remote_models_api(host: str, port: int = 11434) -> list:
    """
    List available Ollama models using HTTP API.
    
    Args:
        host: Remote host IP/hostname
        port: Ollama API port (default 11434)
        
    Returns:
        List of model names
    """
    url = f"http://{host}:{port}/api/tags"
    
    # FIXED: Use TCPConnector with keepalive
    connector = aiohttp.TCPConnector(
        ttl_dns_cache=300,
        limit=100,
        force_close=False,
        enable_cleanup_closed=True
    )
    
    try:
        logger.info(f"Fetching models from {url}")
        
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m['name'] for m in data.get('models', [])]
                    logger.info(f"Found {len(models)} models via API")
                    return models
                else:
                    logger.error(f"API returned status {resp.status}")
                    return []
                    
    except aiohttp.ClientConnectorError:
        logger.error(f"Cannot connect to {url} - is Ollama running and accessible?")
        return []
    except asyncio.TimeoutError:
        logger.error(f"Timeout connecting to {url}")
        return []
    except Exception as e:
        logger.error(f"Error listing models: {e}", exc_info=True)
        return []


async def send_to_ollama_api(host: str, model: str, prompt: str, port: int = 11434, max_retries: int = 3) -> str:
    """
    Send prompt to Ollama via HTTP API (non-streaming) with retry logic.
    
    Args:
        host: Remote host IP/hostname
        model: Model name
        prompt: User prompt
        port: Ollama API port (default 11434)
        max_retries: Number of retry attempts (default 3)
        
    Returns:
        Model response text
    """
    url = f"http://{host}:{port}/api/generate"
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,  # Get complete response at once
        "options": {
            "temperature": 0.7,
        }
    }
    
    logger.info(f"Sending {len(prompt)} characters to {model}")
    print(f"📤 Sending prompt to Ollama API...")
    print(f"   Model: {model}")
    print(f"   Length: {len(prompt)} chars")
    
    # FIXED: TCPConnector with keepalive and no force_close
    connector = aiohttp.TCPConnector(
        ttl_dns_cache=300,
        limit=100,
        force_close=False,  # IMPORTANT: Keep connections alive
        enable_cleanup_closed=True,
        keepalive_timeout=300  # 5 minutes keepalive
    )
    
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # FIXED: Longer timeout for LLM responses (5 minutes)
            timeout = aiohttp.ClientTimeout(
                total=300,  # 5 minutes total
                connect=30,  # 30 seconds to connect
                sock_read=300  # 5 minutes to read response
            )
            
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(url, json=payload, timeout=timeout) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        response = data.get('response', '')
                        
                        logger.info(f"Received response: {len(response)} characters")
                        print(f"✅ Received response: {len(response)} chars")
                        
                        return response
                    else:
                        error_text = await resp.text()
                        logger.error(f"API error {resp.status}: {error_text}")
                        return f"Error: API returned status {resp.status}"
                        
        except asyncio.TimeoutError:
            last_error = "Request timed out after 5 minutes"
            logger.warning(f"Attempt {attempt + 1}/{max_retries}: Timeout")
            if attempt < max_retries - 1:
                print(f"⚠️  Timeout, retrying... ({attempt + 1}/{max_retries})")
                await asyncio.sleep(2)  # Wait 2 seconds before retry
                continue
            else:
                logger.error(last_error)
                return f"Error: {last_error}"
                
        except aiohttp.ServerDisconnectedError:
            last_error = "Server disconnected"
            logger.warning(f"Attempt {attempt + 1}/{max_retries}: Server disconnected")
            if attempt < max_retries - 1:
                print(f"⚠️  Connection lost, retrying... ({attempt + 1}/{max_retries})")
                await asyncio.sleep(2)  # Wait 2 seconds before retry
                continue
            else:
                logger.error(last_error)
                return f"Error: {last_error}. Please check if Ollama is still running."
                
        except aiohttp.ClientConnectorError:
            last_error = f"Cannot connect to Ollama at {host}:{port}"
            logger.error(last_error)
            return f"Error: {last_error}. Check if SSH tunnel is still active."
            
        except Exception as e:
            last_error = str(e)
            logger.error(f"Error sending prompt: {e}", exc_info=True)
            if attempt < max_retries - 1:
                print(f"⚠️  Error occurred, retrying... ({attempt + 1}/{max_retries})")
                await asyncio.sleep(2)
                continue
            else:
                return f"Error: {e}"
    
    return f"Error: {last_error}"


async def send_to_ollama_api_streaming(host: str, model: str, prompt: str, port: int = 11434):
    """
    Send prompt to Ollama via HTTP API with streaming response.
    Yields response chunks as they arrive.
    
    Args:
        host: Remote host IP/hostname
        model: Model name
        prompt: User prompt
        port: Ollama API port (default 11434)
        
    Yields:
        Response text chunks
    """
    url = f"http://{host}:{port}/api/generate"
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,  # Enable streaming
    }
    
    logger.info(f"Streaming prompt to {model}: {len(prompt)} chars")
    
    # FIXED: TCPConnector with keepalive
    connector = aiohttp.TCPConnector(
        ttl_dns_cache=300,
        limit=100,
        force_close=False,
        enable_cleanup_closed=True,
        keepalive_timeout=300
    )
    
    try:
        timeout = aiohttp.ClientTimeout(total=300, sock_read=300)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(url, json=payload, timeout=timeout) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"API error {resp.status}: {error_text}")
                    yield f"Error: API returned status {resp.status}"
                    return
                
                # Read streaming response line by line
                async for line in resp.content:
                    if line:
                        try:
                            chunk_data = json.loads(line)
                            text = chunk_data.get('response', '')
                            
                            if text:
                                yield text
                            
                            # Check if done
                            if chunk_data.get('done', False):
                                break
                                
                        except json.JSONDecodeError:
                            continue
                            
    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        yield f"\nError: {e}"


# ============================================================================
# SSH TERMINAL METHODS (Legacy - Has fragmentation issues)
# ============================================================================

async def list_remote_models(ssh):
    """
    List available Ollama models on remote host via SSH.
    Legacy method - prefer list_remote_models_api() for reliability.
    
    Returns list of model names or empty list if none found.
    """
    try:
        # Check if connection is alive
        if ssh.is_closed():
            logger.error("SSH connection is closed")
            return []
        
        logger.info("Listing remote Ollama models via SSH")
        
        # Try multiple approaches to find ollama
        commands_to_try = [
            'ollama list',  # If in PATH
            '~/.ollama/bin/ollama list',  # Common custom install location
            '/usr/local/bin/ollama list',  # Common system install
            '/usr/bin/ollama list',  # Another common location
            'source ~/.bashrc && ollama list',  # Load shell environment
            'bash -l -c "ollama list"',  # Login shell (loads full profile)
        ]
        
        for cmd in commands_to_try:
            try:
                result = await ssh.run(cmd, check=False)
                
                # Exit status 127 = command not found, try next
                if result.exit_status == 127:
                    continue
                
                out = result.stdout or result.stderr
                
                if out and 'NAME' in out:
                    models = []
                    for line in out.splitlines():
                        line = line.strip()
                        if not line or line.lower().startswith('name'):
                            continue
                        
                        parts = line.split()
                        if parts:
                            models.append(parts[0])
                    
                    if models:
                        logger.info(f"Found {len(models)} models using: {cmd}")
                        return models
            except Exception as e:
                logger.debug(f"Command '{cmd}' failed: {e}")
                continue
        
        logger.warning("No Ollama models found or ollama not installed")
        return []
        
    except Exception as e:
        logger.error(f"Error listing models: {e}", exc_info=True)
        return []


async def start_persistent_ollama(ssh, model: str):
    """
    Start persistent ollama run process and return process handle.
    Uses bash -l -c to load full shell environment.
    
    WARNING: This method has terminal fragmentation issues.
    Consider using the HTTP API methods instead.
    
    Args:
        ssh: AsyncSSH connection
        model: Model name to run
        
    Returns:
        Process handle with stdin/stdout
        
    Raises:
        Exception if process fails to start
    """
    logger.info(f"Starting persistent Ollama process for model: {model}")
    
    try:
        # Use login shell to get full PATH
        command = f'bash -l -c "ollama run {shlex.quote(model)}"'
        
        proc = await ssh.create_process(
            command,
            term_type='xterm',
            encoding=None  # Use binary mode to avoid encoding issues
        )
        
        # Wait longer for Ollama to initialize
        await asyncio.sleep(3)
        
        # Check if process is still alive
        if proc.exit_status is not None:
            logger.error(f"Ollama process exited immediately with status {proc.exit_status}")
            raise Exception(f"Ollama failed to start (exit status: {proc.exit_status})")
        
        logger.info(f"Ollama process started for {model}")
        return proc
        
    except Exception as e:
        logger.error(f"Failed to start Ollama: {e}", exc_info=True)
        raise


async def send_and_stream(proc, prompt: str) -> str:
    """
    Send prompt to Ollama via SSH terminal and stream response.
    
    WARNING: This method has fragmentation issues due to terminal emulation.
    The interactive terminal echoes input character-by-character.
    Consider using send_to_ollama_api() instead.
    
    Args:
        proc: Process handle from start_persistent_ollama
        prompt: User prompt to send
        
    Returns:
        Cleaned response text
    """
    logger.info(f"Sending prompt ({len(prompt)} characters) via SSH terminal")
    
    # Check if stdin is still open
    if proc.stdin.is_closing():
        logger.error("Process stdin is closed")
        raise BrokenPipeError("Process has terminated")
    
    try:
        # Encode and send entire prompt at once
        full_prompt = (prompt + "\n").encode('utf-8')
        proc.stdin.write(full_prompt)
        await proc.stdin.drain()
        
        logger.debug(f"Prompt sent: {len(full_prompt)} bytes")
        
    except Exception as e:
        logger.error(f"Error writing prompt: {e}")
        raise
    
    # Wait for model to start processing
    await asyncio.sleep(1.0)
    
    # Read response
    output = []
    idle_count = 0
    max_idle = config.llm.idle_timeout
    chunk_size = config.llm.stream_chunk_size
    
    while True:
        try:
            chunk = await asyncio.wait_for(
                proc.stdout.read(chunk_size),
                timeout=1.0
            )
            
            if not chunk:
                break
            
            # Decode bytes to string
            try:
                text = chunk.decode('utf-8', errors='ignore')
                output.append(text)
            except Exception as e:
                logger.warning(f"Error decoding chunk: {e}")
            
            # Reset idle counter
            idle_count = 0
            
        except asyncio.TimeoutError:
            idle_count += 1
            
            if idle_count > max_idle:
                logger.debug(f"Idle timeout reached after {max_idle} seconds")
                break
            
            continue
            
        except Exception as e:
            logger.error(f"Error reading output: {e}")
            break
    
    # Combine all chunks
    response = ''.join(output)
    
    # Clean ANSI codes
    response = clean(response)
    
    logger.info(f"Received complete response: {len(response)} characters")
    
    return response