# AMP LLM Theme System - Auto-Discovery

## 🎨 How It Works

The theme system **automatically discovers** any theme files you add to the `webapp/static/` directory!

Just drop a `theme-*.css` file into the static folder and it will instantly appear in the theme picker.

## 📝 Creating a Custom Theme

### Method 1: With Metadata Comments (Recommended)

Add these special comments at the top of your CSS file:

```css
/* ============================================================================
   THEME_NAME: My Awesome Theme
   THEME_COLORS: #FF6B6B, #FFD93D, #6BCB77
   ============================================================================ */
```

**Example:**
```css
/* THEME_NAME: Sunset Vibes
   THEME_COLORS: #FF6B6B, #FFD93D, #6BCB77
*/

body {
    background: linear-gradient(135deg, #FF6B6B 0%, #FFD93D 50%, #6BCB77 100%);
}

/* ... rest of your styles ... */
```

### Method 2: Auto-Generated (Easy)

If you don't add metadata comments, the system will:
1. Extract the theme ID from the filename (`theme-sunset.css` → `sunset`)
2. Auto-generate a display name (`sunset` → `Sunset`)
3. Use default preview colors

## 📁 File Naming Convention

**Required format:** `theme-{name}.css`

✅ Good examples:
- `theme-sunset.css`
- `theme-ocean-blue.css`
- `theme-dark-mode.css`
- `theme-my-custom-theme.css`

❌ Bad examples:
- `sunset.css` (missing "theme-" prefix)
- `mytheme.css` (missing "theme-" prefix)
- `Theme-Sunset.css` (capital T - use lowercase)

## 🎯 Metadata Format

### THEME_NAME
The display name shown in the theme picker dropdown.

```css
/* THEME_NAME: Professional Dark Mode */
```

### THEME_COLORS
Hex color codes for the gradient preview (2-4 colors recommended).

```css
/* THEME_COLORS: #2C3E50, #16A085, #E67E22 */
```

The system will extract colors using this pattern: `#[0-9A-Fa-f]{6}`

## 🚀 Quick Start - Adding a New Theme

1. **Copy an existing theme** as a starting point:
   ```bash
   cp webapp/static/theme-green.css webapp/static/theme-mytheme.css
   ```

2. **Update the metadata** at the top:
   ```css
   /* THEME_NAME: My Custom Theme
      THEME_COLORS: #FF0000, #00FF00, #0000FF
   */
   ```

3. **Customize the colors** throughout the file

4. **Refresh your browser** - the new theme appears automatically!

## 🔍 Theme Discovery Process

When the `/api/themes` endpoint is called:

1. **Scan** for all `theme-*.css` files in `webapp/static/`
2. **Parse** CSS comments for metadata (first 20 lines)
3. **Fallback** to hardcoded metadata if parsing fails
4. **Auto-generate** metadata if file is unknown
5. **Return** sorted list of all themes

## 📦 Built-in Themes

The following themes have fallback metadata:

| File | Display Name | Colors |
|------|-------------|--------|
| `theme-green.css` | Green Primary | `#1BEB49`, `#0E1F81` |
| `theme-blue.css` | Blue Primary | `#0E1F81`, `#1BEB49` |
| `theme-balanced.css` | Tri-Color | `#0E1F81`, `#1BEB49`, `#FFA400` |
| `theme-professional.css` | Professional | `#2C3E50`, `#16A085`, `#E67E22` |
| `theme-company.css` | Company | `#0E1F81`, `#1BEB49`, `#FFA400` |

## 🎨 Example: Complete Custom Theme

See `theme-sunset.css` for a complete working example with:
- ✅ Metadata comments
- ✅ Full color scheme
- ✅ All component styles
- ✅ Landing header styling
- ✅ Hover effects

## 🐛 Troubleshooting

**Theme not appearing?**
1. Check filename starts with `theme-` and ends with `.css`
2. Verify file is in `webapp/static/` directory
3. Check server logs for parsing errors
4. Hard refresh browser (Ctrl+F5)

**Colors not showing?**
1. Verify `THEME_COLORS` format: `#RRGGBB` (6-digit hex)
2. Check for typos in color codes
3. Ensure comment is in first 20 lines of file

**Display name wrong?**
1. Check `THEME_NAME` comment format
2. Remove extra spaces or special characters
3. Verify comment is in first 20 lines

## 💡 Pro Tips

1. **Use existing themes as templates** - they have all the CSS classes you need
2. **Test with different modes** - make sure colors work in Chat, NCT Lookup, etc.
3. **Keep colors accessible** - ensure good contrast for readability
4. **Name themes descriptively** - users will see the display name in the dropdown
5. **Use 2-3 colors in preview** - looks best in the gradient indicator

## 🔧 Server Configuration

The theme discovery is handled in `webapp/server.py`:

```python
@app.get("/api/themes")
async def list_available_themes():
    # Automatically scans static directory
    # Parses CSS comments
    # Returns theme list
    pass
```

No configuration needed - just drop themes in static folder! 🎉