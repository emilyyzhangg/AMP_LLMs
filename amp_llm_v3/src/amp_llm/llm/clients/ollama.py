"""
Enhanced LLM utility functions using the improved session manager.
This upgrades your existing async_llm_utils.py with better reliability.

Key improvements:
- Uses enhanced session manager with auto-tunneling
- Better error handling
- Cleaner API
"""
import asyncio
import aiohttp
import json
import re
from typing import Optional, List, AsyncGenerator
from config import get_config, get_logger

logger = get_logger(__name__)
config = get_config()

# ANSI escape sequence pattern
ANSI_ESCAPE = re.compile(r'(?:\x1B[@-_][0-?]*[ -/]*[@-~])')


def clean(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return ANSI_ESCAPE.sub('', text).strip()


# ============================================================================
# HIGH-LEVEL API METHODS (Recommended)
# ============================================================================

async def list_remote_models_api(host: str, ssh_connection=None, port: int = 11434) -> List[str]:
    """
    List available Ollama models using session manager.
    Automatically handles tunneling if direct connection fails.
    
    Args:
        host: Remote host IP/hostname
        ssh_connection: Optional SSH connection for tunneling
        port: Ollama API port (default: 11434)
        
    Returns:
        List of model names
    """
    from llm.utils.session import OllamaSessionManager
    
    try:
        async with OllamaSessionManager(host, port, ssh_connection) as session:
            return await session.list_models()
    
    except Exception as e:
        logger.error(f"Error listing models: {e}", exc_info=True)
        return []


async def send_to_ollama_api(
    host: str,
    model: str,
    prompt: str,
    ssh_connection=None,
    port: int = 11434,
    system: Optional[str] = None,
    temperature: float = 0.7,
    max_retries: int = 3
) -> str:
    """
    Send prompt to Ollama using session manager.
    Automatically handles tunneling and retries.
    
    Args:
        host: Remote host IP/hostname
        model: Model name
        prompt: User prompt
        ssh_connection: Optional SSH connection for tunneling
        port: Ollama API port (default: 11434)
        system: Optional system prompt
        temperature: Temperature setting
        max_retries: Maximum retry attempts
        
    Returns:
        Model response text
    """
    from llm.utils.session import OllamaSessionManager
    
    try:
        async with OllamaSessionManager(host, port, ssh_connection) as session:
            return await session.send_prompt(
                model=model,
                prompt=prompt,
                system=system,
                temperature=temperature,
                max_retries=max_retries
            )
    
    except Exception as e:
        logger.error(f"Error sending prompt: {e}", exc_info=True)
        return f"Error: {e}"


async def send_to_ollama_api_streaming(
    host: str,
    model: str,
    prompt: str,
    ssh_connection=None,
    port: int = 11434,
    system: Optional[str] = None,
    temperature: float = 0.7
) -> AsyncGenerator[str, None]:
    """
    Send prompt to Ollama with streaming response.
    Automatically handles tunneling.
    
    Args:
        host: Remote host IP/hostname
        model: Model name
        prompt: User prompt
        ssh_connection: Optional SSH connection for tunneling
        port: Ollama API port
        system: Optional system prompt
        temperature: Temperature setting
        
    Yields:
        Response text chunks
    """
    from llm.utils.session import OllamaSessionManager
    
    try:
        # Create session
        session_manager = OllamaSessionManager(host, port, ssh_connection)
        await session_manager.start_session()
        
        # Build payload
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature
            }
        }
        
        if system:
            payload["system"] = system
        
        url = f"{session_manager.base_url}/api/generate"
        
        logger.info(f"Streaming from {model}: {len(prompt)} chars")
        
        try:
            async with session_manager.session.post(url, json=payload) as resp:
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
                            
                            if 'response' in chunk_data:
                                yield chunk_data['response']
                            
                            # Check if done
                            if chunk_data.get('done', False):
                                break
                        
                        except json.JSONDecodeError:
                            continue
        
        finally:
            await session_manager.close_session()
    
    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        yield f"\nError: {e}"


# ============================================================================
# CONVENIENCE WRAPPERS
# ============================================================================

async def quick_ollama_query(
    ssh_connection,
    model: str,
    prompt: str,
    system: Optional[str] = None
) -> str:
    """
    Quick one-off query using SSH connection.
    Automatically determines host from SSH connection.
    
    Args:
        ssh_connection: AsyncSSH connection
        model: Model name
        prompt: User prompt
        system: Optional system prompt
        
    Returns:
        Response text
    """
    try:
        host = ssh_connection._host if hasattr(ssh_connection, '_host') else config.network.default_ip
    except:
        host = config.network.default_ip
    
    return await send_to_ollama_api(
        host=host,
        model=model,
        prompt=prompt,
        ssh_connection=ssh_connection,
        system=system
    )


# ============================================================================
# LEGACY SSH TERMINAL METHODS (Keep for backward compatibility)
# ============================================================================

async def list_remote_models(ssh):
    """
    List available Ollama models on remote host via SSH.
    Legacy method - prefer list_remote_models_api() for reliability.
    
    Returns:
        List of model names or empty list if none found
    """
    try:
        if ssh.is_closed():
            logger.error("SSH connection is closed")
            return []
        
        logger.info("Listing remote Ollama models via SSH")
        
        commands_to_try = [
            'ollama list',
            '~/.ollama/bin/ollama list',
            '/usr/local/bin/ollama list',
            '/usr/bin/ollama list',
            'source ~/.bashrc && ollama list',
            'bash -l -c "ollama list"',
        ]
        
        for cmd in commands_to_try:
            try:
                result = await ssh.run(cmd, check=False)
                
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


# NOTE: start_persistent_ollama and send_and_stream from old version
# are kept for backward compatibility but NOT recommended.
# They have terminal fragmentation issues. Use API methods instead.


# ============================================================================
# CONNECTION TESTING
# ============================================================================

async def test_ollama_connection(host: str, port: int = 11434) -> bool:
    """
    Test if Ollama is accessible at given host:port.
    
    Args:
        host: Host to test
        port: Port to test
        
    Returns:
        True if accessible
    """
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"http://{host}:{port}/api/tags") as resp:
                return resp.status == 200
    except Exception:
        return False


async def get_ollama_info(host: str, ssh_connection=None, port: int = 11434) -> dict:
    """
    Get information about Ollama server.
    
    Args:
        host: Remote host
        ssh_connection: Optional SSH connection
        port: Ollama port
        
    Returns:
        Dictionary with server info
    """
    from llm.utils.session import OllamaSessionManager
    
    info = {
        "accessible": False,
        "models": [],
        "using_tunnel": False,
        "host": host,
        "port": port
    }
    
    try:
        async with OllamaSessionManager(host, port, ssh_connection) as session:
            info["accessible"] = await session.is_alive()
            info["using_tunnel"] = session._using_tunnel
            
            if info["accessible"]:
                info["models"] = await session.list_models()
    
    except Exception as e:
        logger.error(f"Error getting Ollama info: {e}")
    
    return info