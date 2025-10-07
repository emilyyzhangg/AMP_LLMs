"""
LLM utility functions for Ollama interaction.
Improved with configurable timeouts and better error handling.
"""
import asyncio
import shlex
import re
from config import get_config, get_logger

logger = get_logger(__name__)
config = get_config()

# ANSI escape sequence pattern
ANSI_ESCAPE = re.compile(r'(?:\x1B[@-_][0-?]*[ -/]*[@-~])')


def clean(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return ANSI_ESCAPE.sub('', text).strip()


async def list_remote_models(ssh):
    """
    List available Ollama models on remote host.
    Returns list of model names or empty list if none found.
    """
    try:
        # Check if connection is alive
        if ssh.is_closed():
            logger.error("SSH connection is closed")
            return []
        
        logger.info("Listing remote Ollama models")
        
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
    Send prompt to Ollama and stream response until idle timeout.
    
    Args:
        proc: Process handle from start_persistent_ollama
        prompt: User prompt to send
        
    Returns:
        Cleaned response text
    """
    logger.debug(f"Sending prompt: {prompt[:50]}...")
    
    # Check if stdin is still open
    if proc.stdin.is_closing():
        logger.error("Process stdin is closed")
        raise BrokenPipeError("Process has terminated")
    
    # Write prompt with explicit newline - ollama needs this to know prompt is complete
    try:
        full_prompt = prompt + "\n"
        proc.stdin.write(full_prompt.encode('utf-8'))
        await proc.stdin.drain()
    except Exception as e:
        logger.error(f"Error writing prompt: {e}")
        raise
    
    # Read response - skip echoed input and wait for actual model output
    output = []
    idle_count = 0
    max_idle = 10  # Increase timeout for large inputs
    seen_response_start = False
    echo_buffer = ""
    
    while True:
        try:
            chunk = await asyncio.wait_for(
                proc.stdout.read(1024),
                timeout=2.0
            )
            
            if not chunk:
                break
            
            # Decode bytes to string
            try:
                text = chunk.decode('utf-8', errors='ignore')
                
                # Skip the echoed prompt (ollama echoes input back)
                if not seen_response_start:
                    echo_buffer += text
                    # Look for the response marker (usually after the echoed prompt)
                    if '\n' in echo_buffer or len(echo_buffer) > len(prompt) + 100:
                        # Found start of real response
                        seen_response_start = True
                        # Everything after the prompt is the response
                        response_start = echo_buffer.find('\n', len(prompt))
                        if response_start != -1:
                            output.append(echo_buffer[response_start:])
                        echo_buffer = ""
                else:
                    # We're in the actual response now
                    output.append(text)
                
            except Exception as e:
                logger.warning(f"Error decoding chunk: {e}")
            
            idle_count = 0  # Reset idle counter when we get data
            
        except asyncio.TimeoutError:
            idle_count += 1
            if idle_count > max_idle:
                logger.debug(f"Idle timeout reached after {max_idle} seconds")
                break
            continue
        except Exception as e:
            logger.error(f"Error reading output: {e}")
            break
    
    response = clean(''.join(output))
    logger.debug(f"Received response: {len(response)} characters")
    
    return response if response else "No response received from model."