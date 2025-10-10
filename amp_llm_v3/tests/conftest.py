# tests/conftest.py
import pytest
from amp_llm.core.context import ApplicationContext

@pytest.fixture
async def app_context():
    """Provide test application context."""
    context = ApplicationContext()
    yield context
    # Cleanup

@pytest.fixture
def mock_ssh_connection():
    """Mock SSH connection for testing."""
    # Implementation