# In amp_llm_v3/src/amp_llm/core/__init__.py
# Add these imports:

from .interrupt_handler import (
    handle_interrupts,
    safe_ainput,
    check_for_menu_exit,
    run_with_interrupt_protection,
    InterruptContext,
    InterruptSignal,
)

# Add to __all__:
__all__ = [
    # ... existing exports ...
    'handle_interrupts',
    'safe_ainput',
    'check_for_menu_exit',
    'run_with_interrupt_protection',
    'InterruptContext',
    'InterruptSignal',
]