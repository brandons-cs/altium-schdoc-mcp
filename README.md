# altium-schdoc-mcp

Offline Altium `.SchDoc` parser — CLI tool + MCP server for AI-assisted hardware review.

Parses Altium Designer schematic documents (binary OLE2 format) without requiring Altium Designer installed. Extracts structured component, net, pin, and hierarchy data as JSON or Markdown.

## Features

- **No Altium required** — pure offline parsing via `olefile`
- **CLI tool** — `parse-schdoc` command for terminal usage
- **MCP server** — 5 tools for VS Code Copilot / Claude Desktop integration
- **JSON + Markdown output** — structured data for automation, readable summaries for AI reasoning
- **Net resolution** — traces wire connectivity between pins, ports, net labels, and power ports
- **Batch processing** — parse entire schematic directories in one command
- **Zero config** — works on Python 3.10+ with a single dependency (`olefile`)

## Installation

```bash
git clone https://github.com/brandons-cs/altium-schdoc-mcp.git
cd altium-schdoc-mcp
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -e .
```

For MCP server support:
```bash
pip install -e ".[mcp]"
```

## CLI Usage

```bash
# JSON to stdout
parse-schdoc path/to/schematic.SchDoc

# JSON to file
parse-schdoc path/to/schematic.SchDoc -o output.json

# Markdown to stdout
parse-schdoc path/to/schematic.SchDoc --markdown

# Markdown to file
parse-schdoc path/to/schematic.SchDoc --markdown -o output.md

# Batch — process all SchDoc files in a directory
parse-schdoc --batch path/to/schematics/ --markdown -o path/to/output/
```

## MCP Server

### VS Code Setup

Add to `.vscode/mcp.json` in your project:
```json
{
    "servers": {
        "altium-schdoc": {
            "type": "stdio",
            "command": "C:/Projects/altium-schdoc-mcp/.venv/Scripts/python.exe",
            "args": ["-m", "src.mcp_server"],
            "cwd": "C:/Projects/altium-schdoc-mcp"
        }
    }
}
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `parse_schdoc_json` | Parse a SchDoc file → structured JSON |
| `parse_schdoc_markdown` | Parse a SchDoc file → LLM-readable Markdown |
| `list_schematics` | List all SchDoc files in a directory |
| `search_component` | Search components by designator/value/description (regex) |
| `get_net_connections` | Get all pins connected to a net (regex) |

### Example Copilot Queries

With the MCP server running, you can ask Copilot:
- "What components are on the DUT 1 IO schematic?"
- "List all relay designators across all schematics"
- "What pins are connected to the 24VDC net?"
- "Show me the E-Stop safety chain components"

## Output Format

### JSON Structure

```json
{
  "metadata": {
    "filename": "Schematic.SchDoc",
    "parser_version": "0.1.0"
  },
  "components": [
    {
      "designator": "Rly301",
      "library_reference": "WAGO - Relay, 857-304",
      "description": "24V 1CO 6A Relay and Base",
      "footprint": "",
      "value": "857-304",
      "parameters": {"Value": "857-304"},
      "pins": [
        {"designator": "A1", "name": "A1", "electrical": "Passive"},
        {"designator": "11", "name": "11", "electrical": "Passive"}
      ]
    }
  ],
  "nets": {
    "E-Stop 1(1)": ["Rly201.A1", "WN?.0", "[Port]E-Stop 1(1)"],
    "24VDC": ["PS1.4", "EC1.3"]
  },
  "pins": [...],
  "ports": [
    {"name": "24VDC (Ctrl)", "io_type": "Input", "x": 100.0, "y": 200.0}
  ],
  "power_ports": [
    {"name": "GND", "style": "PowerGround"}
  ],
  "hierarchy": []
}
```

### Markdown Summary

The Markdown output includes:
- **Component table** — designator, library ref, value, footprint, description
- **Power rails** — named power nets with styles
- **Ports** — inter-sheet connections with IO types
- **Net list** — net name → connected pins (component.pin format)
- **Pin map** — per-component pin details (designator, name, electrical type)
- **Hierarchy** — sheet symbols with child sheet references

## How It Works

1. Opens the `.SchDoc` file as an OLE2 compound document via `olefile`
2. Reads the `FileHeader` stream — a sequence of length-prefixed, pipe-delimited key-value records
3. Parses each record by its `RECORD` type ID (1=component, 2=pin, 17=power port, 25=net label, 27=wire, etc.)
4. Resolves parent-child relationships via `OWNERINDEX` (0-based ordinal after the header record)
5. Calculates pin hot-points (connection coordinates) from body position + pin length × rotation direction
6. Builds a union-find connectivity graph from wire segments and junctions
7. Maps pins → wires → net labels/ports to resolve per-net connectivity

## Supported Record Types

| ID | Type | Extracted Data |
|----|------|----------------|
| 1 | Component | designator, library ref, description, part count |
| 2 | Pin | designator, name, electrical type, position |
| 15 | Sheet Symbol | child sheet reference, dimensions |
| 16 | Sheet Entry | name, IO type |
| 17 | Power Port | net name, style |
| 18 | Port | name, IO type (inter-sheet connection) |
| 25 | Net Label | net name, position |
| 27 | Wire | endpoint coordinates |
| 29 | Junction | position (wire merge point) |
| 31 | Sheet | sheet style, fonts |
| 34 | Designator | reference designator text |
| 41 | Parameter | name-value pairs (component values, comments) |
| 45 | Implementation | footprint model name, type |

## Limitations

- **Net resolution is coordinate-based** — uses a tolerance of ±2 Altium units. Some connections may be missed on schematics with unusual pin lengths or non-standard placement.
- **Cross-sheet hierarchy** — the parser works per-sheet. Full cross-sheet net resolution requires parsing the `.PrjPCB` project file (planned for v0.2).
- **No rendering** — outputs data only, not visual schematic images.
- **Tested with Altium Designer v20-v24** — older or newer format versions may have undocumented record types.

## License

MIT — see [LICENSE](LICENSE).
