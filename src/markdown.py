"""
Convert parsed SchDoc data to LLM-readable Markdown.
"""


def to_markdown(data: dict) -> str:
    """Convert parsed SchDoc dict to a Markdown summary.
    
    Args:
        data: Output from parse_schdoc().
        
    Returns:
        Markdown string.
    """
    lines = []
    meta = data.get("metadata", {})
    filename = meta.get("filename", "Unknown")

    lines.append(f"# Schematic: {filename}")
    lines.append("")
    lines.append(f"- **Parser version:** {meta.get('parser_version', '?')}")
    lines.append(f"- **Components:** {len(data.get('components', []))}")
    lines.append(f"- **Nets:** {len(data.get('nets', {}))}")
    lines.append(f"- **Ports:** {len(data.get('ports', []))}")
    lines.append(f"- **Power rails:** {len(data.get('power_ports', []))}")
    lines.append("")

    # --- Components ---
    components = data.get("components", [])
    if components:
        lines.append("## Components")
        lines.append("")
        lines.append("| Designator | Library Reference | Value | Footprint | Description |")
        lines.append("|------------|-------------------|-------|-----------|-------------|")
        for c in components:
            desig = c.get("designator", "").replace("|", "\\|")
            libref = c.get("library_reference", "").replace("|", "\\|")
            value = c.get("value", "").replace("|", "\\|")
            fp = c.get("footprint", "").replace("|", "\\|")
            desc = c.get("description", "").replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {desig} | {libref} | {value} | {fp} | {desc} |"
            )
        lines.append("")

    # --- Power Ports ---
    power_ports = data.get("power_ports", [])
    if power_ports:
        lines.append("## Power Rails")
        lines.append("")
        lines.append("| Name | Style |")
        lines.append("|------|-------|")
        for pp in power_ports:
            lines.append(f"| {pp['name']} | {pp.get('style', '')} |")
        lines.append("")

    # --- Ports (inter-sheet) ---
    ports = data.get("ports", [])
    if ports:
        lines.append("## Ports (Inter-Sheet Connections)")
        lines.append("")
        lines.append("| Name | IO Type |")
        lines.append("|------|---------|")
        for p in ports:
            lines.append(f"| {p['name']} | {p.get('io_type', '')} |")
        lines.append("")

    # --- Nets ---
    nets = data.get("nets", {})
    if nets:
        lines.append("## Nets")
        lines.append("")
        for net_name, pins in sorted(nets.items()):
            lines.append(f"### {net_name}")
            lines.append("")
            for pin in sorted(pins):
                lines.append(f"- {pin}")
            lines.append("")

    # --- Pin Map ---
    components_with_pins = [c for c in components if c.get("pins")]
    if components_with_pins:
        lines.append("## Pin Map")
        lines.append("")
        for c in components_with_pins:
            desig = c.get("designator", "(no desig)")
            libref = c.get("library_reference", "")
            lines.append(f"### {desig} ({libref})")
            lines.append("")
            lines.append("| Pin | Name | Electrical Type |")
            lines.append("|-----|------|-----------------|")
            for pin in c.get("pins", []):
                lines.append(
                    f"| {pin['designator']} | {pin['name']} | {pin['electrical']} |"
                )
            lines.append("")

    # --- Hierarchy ---
    hierarchy = data.get("hierarchy", [])
    if hierarchy:
        lines.append("## Sheet Hierarchy")
        lines.append("")
        for sheet in hierarchy:
            name = sheet.get("sheet_name", "")
            fname = sheet.get("sheet_filename", "")
            lines.append(f"### {name or fname}")
            if fname:
                lines.append(f"- **File:** {fname}")
            entries = sheet.get("entries", [])
            if entries:
                lines.append("- **Entries:**")
                for e in entries:
                    lines.append(f"  - {e['name']} ({e.get('io_type', '')})")
            lines.append("")

    return "\n".join(lines)
