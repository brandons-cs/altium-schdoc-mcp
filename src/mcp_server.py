"""
MCP server for Altium SchDoc parsing.

Exposes tools for parsing SchDoc files, generating Markdown summaries,
listing schematics, searching components, and querying net connections.

Run with: python -m src.mcp_server
Or via MCP: configured in VS Code / Claude Desktop MCP settings.
"""

import json
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.parser import parse_schdoc
from src.markdown import to_markdown

mcp = FastMCP(
    "altium-schdoc",
    instructions="Offline Altium SchDoc parser — extract components, nets, pins, and hierarchy from .SchDoc files without Altium Designer.",
)

# Cache parsed results keyed by absolute file path
_cache: dict[str, dict] = {}


def _get_parsed(file_path: str) -> dict:
    """Parse a SchDoc file, using cache if available."""
    abs_path = str(Path(file_path).resolve())
    if abs_path not in _cache:
        _cache[abs_path] = parse_schdoc(abs_path)
    return _cache[abs_path]


@mcp.tool()
def parse_schdoc_json(file_path: str) -> str:
    """Parse an Altium .SchDoc file and return structured JSON.
    
    Returns component list, net connectivity, pin mappings, ports, 
    power rails, and sheet hierarchy.
    
    Args:
        file_path: Absolute or relative path to the .SchDoc file.
    """
    data = _get_parsed(file_path)
    return json.dumps(data, indent=2, ensure_ascii=False)


@mcp.tool()
def parse_schdoc_markdown(file_path: str) -> str:
    """Parse an Altium .SchDoc file and return an LLM-readable Markdown summary.
    
    Includes component table, net list, pin map, ports, power rails, 
    and hierarchy — formatted for AI reasoning.
    
    Args:
        file_path: Absolute or relative path to the .SchDoc file.
    """
    data = _get_parsed(file_path)
    return to_markdown(data)


@mcp.tool()
def list_schematics(directory: str) -> str:
    """List all .SchDoc files in a directory.
    
    Args:
        directory: Path to search for .SchDoc files.
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return f"Error: {directory} is not a directory"
    
    files = sorted(dir_path.glob("*.SchDoc"))
    if not files:
        return f"No .SchDoc files found in {directory}"
    
    result = [f"Found {len(files)} SchDoc files in {directory}:\n"]
    for f in files:
        result.append(f"- {f.name}")
    return "\n".join(result)


@mcp.tool()
def search_component(file_path: str, pattern: str) -> str:
    """Search for components in a SchDoc file by designator, value, or description.
    
    Uses regex pattern matching (case-insensitive).
    
    Args:
        file_path: Path to the .SchDoc file.
        pattern: Regex pattern to match against designator, value, library_reference, or description.
    """
    data = _get_parsed(file_path)
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"Invalid regex pattern '{pattern}': {e}"
    
    matches = []
    for comp in data.get("components", []):
        fields = [
            comp.get("designator", ""),
            comp.get("value", ""),
            comp.get("library_reference", ""),
            comp.get("description", ""),
        ]
        if any(regex.search(f) for f in fields):
            matches.append(comp)
    
    if not matches:
        return f"No components matching '{pattern}' in {Path(file_path).name}"
    
    return json.dumps(matches, indent=2, ensure_ascii=False)


@mcp.tool()
def get_net_connections(file_path: str, net_name: str) -> str:
    """Get all pins connected to a specific net in a SchDoc file.
    
    Args:
        file_path: Path to the .SchDoc file.
        net_name: Name of the net (case-insensitive search, supports regex).
    """
    data = _get_parsed(file_path)
    nets = data.get("nets", {})
    try:
        regex = re.compile(net_name, re.IGNORECASE)
    except re.error as e:
        return f"Invalid regex pattern '{net_name}': {e}"
    
    matches = {}
    for name, pins in nets.items():
        if regex.search(name):
            matches[name] = pins
    
    if not matches:
        available = list(nets.keys())[:20]
        return f"No net matching '{net_name}'. Available nets (first 20): {', '.join(available)}"
    
    return json.dumps(matches, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
