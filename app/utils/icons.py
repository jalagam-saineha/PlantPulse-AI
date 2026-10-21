"""
A small hand-built inline SVG icon set, used instead of an external icon
font/CDN so the app renders identically offline. Each icon is a 24x24
stroke-style glyph; color is inherited via currentColor.
"""

_WRAP = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true">{inner}</svg>'
)

_ICONS = {
    "grid": '<rect x="3" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5"/>',
    "leaf": '<path d="M4 20c8 0 15-6 16-16-9 1-16 7-16 16z"/><path d="M6 18c2-4 5-7 10-9"/>',
    "film": '<rect x="3" y="4.5" width="18" height="15" rx="2"/><path d="M8 4.5v15M16 4.5v15M3 9.5h5M16 9.5h5M3 15h5M16 15h5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 7v5l3.5 2"/>',
    "sprout": '<path d="M12 21v-8"/><path d="M12 13c0-4-3-6-7-6 0 4 3 7 7 6z"/><path d="M12 11c0-3.5 2.5-5.5 6-5.5 0 3.5-2.5 5.7-6 5.5z"/>',
    "file-text": '<path d="M6 3h8l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3v5h5"/><path d="M8.5 12.5h7M8.5 16h7M8.5 9h3"/>',
    "activity": '<path d="M3 12h4l2.5 7L14 5l2.5 7H21"/>',
    "bar-chart": '<path d="M5 20V10M12 20V4M19 20v-7"/>',
    "columns": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16"/>',
    "bell": '<path d="M6 9a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 13a1.7 1.7 0 0 0 .33 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.33 1.7 1.7 0 0 0-1 1.55V19a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.56 1.7 1.7 0 0 0-1.87.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .33-1.87 1.7 1.7 0 0 0-1.55-1H4a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.56-1 1.7 1.7 0 0 0-.33-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.33H10a1.7 1.7 0 0 0 1-1.55V4a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.56 1.7 1.7 0 0 0 1.87-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.33 1.87V10c.14.41.42.76.79.99.24.14.51.22.79.24H20a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1.01z"/>',
    "server": '<rect x="3" y="4" width="18" height="7" rx="1.5"/><rect x="3" y="13" width="18" height="7" rx="1.5"/><circle cx="7" cy="7.5" r="0.8" fill="currentColor" stroke="none"/><circle cx="7" cy="16.5" r="0.8" fill="currentColor" stroke="none"/>',
    "help-circle": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.2a2.5 2.5 0 1 1 3.7 2.4c-.9.5-1.2 1-1.2 2"/><circle cx="12" cy="17" r="0.6" fill="currentColor" stroke="none"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M20 20l-4.4-4.4"/>',
    "sun": '<circle cx="12" cy="12" r="4.5"/><path d="M12 2.5v2.5M12 19v2.5M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2.5 12H5M19 12h2.5M4.2 19.8L6 18M18 6l1.8-1.8"/>',
    "moon": '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z"/>',
    "chevron-left": '<path d="M14.5 5.5L8 12l6.5 6.5"/>',
    "menu": '<path d="M4 6.5h16M4 12h16M4 17.5h16"/>',
    "log-out": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/>',
    "user": '<circle cx="12" cy="8.5" r="3.5"/><path d="M4.5 20c1.4-3.8 4.6-6 7.5-6s6.1 2.2 7.5 6"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "upload-cloud": '<path d="M7 17.5a4.5 4.5 0 0 1-.7-8.94A6 6 0 0 1 18 8a4.5 4.5 0 0 1 .5 9H16"/><path d="M12 12v8"/><path d="M9.5 14.5L12 12l2.5 2.5"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16.5 9"/>',
    "alert-triangle": '<path d="M12 4.5L21 19H3z"/><path d="M12 10v4"/><circle cx="12" cy="17" r="0.6" fill="currentColor" stroke="none"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3.5 6l8.5 6.5L20.5 6"/>',
    "lock": '<rect x="4.5" y="10.5" width="15" height="9.5" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
    "arrow-right": '<path d="M5 12h14M13 6l6 6-6 6"/>',
}


def icon_svg(name: str, size: int = 18) -> str:
    inner = _ICONS.get(name, _ICONS["help-circle"])
    svg = _WRAP.format(inner=inner)
    return svg.replace('viewBox="0 0 24 24"', f'viewBox="0 0 24 24" width="{size}" height="{size}"')
