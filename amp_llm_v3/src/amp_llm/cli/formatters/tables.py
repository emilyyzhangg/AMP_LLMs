# =============================================================================
# Table Formatting
# =============================================================================

def format_table(
    data: List[Dict[str, Any]],
    headers: Optional[List[str]] = None,
    max_width: Optional[int] = None,
    align: Optional[Dict[str, str]] = None,
) -> str:
    """
    Format data as ASCII table.
    
    Args:
        data: List of dictionaries
        headers: Optional header names (defaults to dict keys)
        max_width: Maximum column width
        align: Column alignment (left, right, center)
    
    Returns:
        Formatted table string
    
    Example:
        >>> data = [
        ...     {"name": "Alice", "age": 30, "city": "NYC"},
        ...     {"name": "Bob", "age": 25, "city": "LA"},
        ... ]
        >>> print(format_table(data))
        ┌───────┬─────┬──────┐
        │ Name  │ Age │ City │
        ├───────┼─────┼──────┤
        │ Alice │  30 │ NYC  │
        │ Bob   │  25 │ LA   │
        └───────┴─────┴──────┘
    """
    if not data:
        return "No data to display"
    
    # Get headers
    if headers is None:
        headers = list(data[0].keys())
    
    # Calculate column widths
    col_widths = {}
    for header in headers:
        # Start with header width
        col_widths[header] = len(str(header))
        
        # Check data widths
        for row in data:
            value = str(row.get(header, ""))
            if max_width and len(value) > max_width:
                value = value[:max_width - 3] + "..."
            col_widths[header] = max(col_widths[header], len(value))
    
    # Default alignment
    if align is None:
        align = {header: 'left' for header in headers}
    
    # Build table
    lines = []
    
    # Top border
    lines.append("┌" + "┬".join("─" * (col_widths[h] + 2) for h in headers) + "┐")
    
    # Headers
    header_cells = []
    for header in headers:
        cell = f" {header.title()} "
        # Pad to width
        padding = col_widths[header] - len(header)
        cell = cell + " " * padding
        header_cells.append(cell)
    
    lines.append("│" + "│".join(header_cells) + "│")
    
    # Header separator
    lines.append("├" + "┼".join("─" * (col_widths[h] + 2) for h in headers) + "┤")
    
    # Data rows
    for row in data:
        row_cells = []
        for header in headers:
            value = str(row.get(header, ""))
            
            # Truncate if needed
            if max_width and len(value) > max_width:
                value = value[:max_width - 3] + "..."
            
            # Align
            col_align = align.get(header, 'left')
            if col_align == 'right':
                value = value.rjust(col_widths[header])
            elif col_align == 'center':
                value = value.center(col_widths[header])
            else:  # left
                value = value.ljust(col_widths[header])
            
            row_cells.append(f" {value} ")
        
        lines.append("│" + "│".join(row_cells) + "│")
    
    # Bottom border
    lines.append("└" + "┴".join("─" * (col_widths[h] + 2) for h in headers) + "┘")
    
    return "\n".join(lines)


def format_simple_table(data: List[Dict[str, Any]]) -> str:
    """
    Format data as simple table (no borders).
    
    Args:
        data: List of dictionaries
    
    Returns:
        Formatted table string
    """
    if not data:
        return "No data to display"
    
    headers = list(data[0].keys())
    
    # Calculate column widths
    col_widths = {}
    for header in headers:
        col_widths[header] = len(str(header))
        for row in data:
            col_widths[header] = max(col_widths[header], len(str(row.get(header, ""))))
    
    # Build table
    lines = []
    
    # Headers
    header_line = "  ".join(h.ljust(col_widths[h]) for h in headers)
    lines.append(colorize(header_line, "cyan", bold=True))
    
    # Separator
    lines.append("  ".join("─" * col_widths[h] for h in headers))
    
    # Data
    for row in data:
        row_line = "  ".join(str(row.get(h, "")).ljust(col_widths[h]) for h in headers)
        lines.append(row_line)
    
    return "\n".join(lines)
