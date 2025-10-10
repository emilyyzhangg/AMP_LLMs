"""
tests/unit/core/test_menu.py
"""

import pytest
from amp_llm.core import MenuSystem, MenuItem, MenuAction, ApplicationContext


@pytest.fixture
def app_context():
    """Create application context for testing."""
    return ApplicationContext()


@pytest.fixture
def menu_system(app_context):
    """Create menu system for testing."""
    return MenuSystem(app_context)


def test_menu_item_creation():
    """Test creating menu item."""
    async def handler():
        return MenuAction.CONTINUE
    
    item = MenuItem(
        key="1",
        name="Test Item",
        handler=handler,
        description="Test description",
    )
    
    assert item.key == "1"
    assert item.name == "Test Item"
    assert item.enabled is True


@pytest.mark.asyncio
async def test_add_menu_item(menu_system):
    """Test adding menu item."""
    async def handler():
        return MenuAction.CONTINUE
    
    menu_system.add_item("99", "Test", handler)
    
    item = menu_system.get_item("99")
    assert item is not None
    assert item.name == "Test"


@pytest.mark.asyncio
async def test_register_alias(menu_system):
    """Test registering alias."""
    async def handler():
        return MenuAction.CONTINUE
    
    menu_system.add_item("99", "Test", handler)
    menu_system.register_alias("test", "99")
    
    assert "test" in menu_system.aliases
    assert menu_system.aliases["test"] == "99"


@pytest.mark.asyncio
async def test_enable_disable_item(menu_system):
    """Test enabling and disabling menu items."""
    async def handler():
        return MenuAction.CONTINUE
    
    menu_system.add_item("99", "Test", handler)
    
    # Initially enabled
    assert menu_system.get_item("99").enabled is True
    
    # Disable
    menu_system.disable_item("99")
    assert menu_system.get_item("99").enabled is False
    
    # Enable
    menu_system.enable_item("99")
    assert menu_system.get_item("99").enabled is True