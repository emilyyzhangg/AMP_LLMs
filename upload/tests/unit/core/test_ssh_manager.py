"""
tests/unit/core/test_ssh_manager.py
"""

import pytest
from unittest.mock import AsyncMock, patch
from amp_llm.core import SSHManager, SSHConnectionError


@pytest.fixture
def ssh_manager():
    """Create SSH manager for testing."""
    return SSHManager()


@pytest.mark.asyncio
async def test_ssh_manager_initialization(ssh_manager):
    """Test SSH manager initialization."""
    assert ssh_manager.connection is None
    assert not ssh_manager.is_connected()


@pytest.mark.asyncio
async def test_is_connected_when_not_connected(ssh_manager):
    """Test is_connected returns False when not connected."""
    assert ssh_manager.is_connected() is False


@pytest.mark.asyncio
async def test_is_connected_when_connected(ssh_manager):
    """Test is_connected returns True when connected."""
    # Mock connection
    mock_conn = AsyncMock()
    mock_conn.is_closed.return_value = False
    ssh_manager.connection = mock_conn
    
    assert ssh_manager.is_connected() is True


@pytest.mark.asyncio
async def test_close(ssh_manager):
    """Test connection closing."""
    # Setup mock connection
    mock_conn = AsyncMock()
    ssh_manager.connection = mock_conn
    
    # Close
    await ssh_manager.close()
    
    # Verify
    mock_conn.close.assert_called_once()
    assert ssh_manager.connection is None


@pytest.mark.asyncio
async def test_run_command_when_not_connected(ssh_manager):
    """Test run_command raises error when not connected."""
    with pytest.raises(SSHConnectionError):
        await ssh_manager.run_command("ls")