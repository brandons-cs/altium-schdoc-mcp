# altium-schdoc-mcp

Read Altium Designer schematic files (`.SchDoc`) without Altium installed.

Extracts components, nets, pins, ports, and hierarchy into JSON or Markdown. Works as a command-line tool or as an [MCP server](https://modelcontextprotocol.io/) so VS Code Copilot / Claude can answer questions about your schematics.

## What problem does this solve?

Altium `.SchDoc` files are binary. You can't open them in a text editor, and you need an Altium license to view them. This tool reads the binary format directly and gives you the data in a usable form.

## Requirements

- Python 3.10 or newer
- No Altium license required

## Installation

```bash
git clone https://github.com/brandons-cs/altium-schdoc-mcp.git
cd altium-schdoc-mcp
python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows (PowerShell)
.venv\Scripts\activate

# Windows (cmd)
.venv\Scripts\activate.bat

# Linux / macOS
source .venv/bin/activate
```

Install the tool:

```bash
pip install -e .
```

To also use the MCP server (for VS Code Copilot / Claude):

```bash
pip install -e ".[mcp]"
```

## CLI Usage

Parse a single file:

```bash
# Print JSON to terminal
parse-schdoc path/to/schematic.SchDoc

# Save JSON to a file
parse-schdoc path/to/schematic.SchDoc -o output.json

# Print Markdown to terminal
parse-schdoc path/to/schematic.SchDoc --markdown

# Save Markdown to a file
parse-schdoc path/to/schematic.SchDoc --markdown -o output.md
```

Parse all `.SchDoc` files in a folder:

```bash
parse-schdoc --batch path/to/schematics/ --markdown -o path/to/output/
```

## MCP Server (VS Code / Claude)

The MCP server lets an AI assistant read your schematics on demand. You don't need to pre-parse anything — the assistant calls the tool when it needs the data.

### Setup

Create a file called `.vscode/mcp.json` in your project:

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

Replace the `command` path with the actual path to your Python executable inside the `.venv`.

Reload VS Code after saving the file. The MCP server will appear in the Copilot tools list.

### Available Tools

| Tool | What it does |
|------|--------------|
| `parse_schdoc_json` | Returns all schematic data as JSON |
| `parse_schdoc_markdown` | Returns a readable summary (tables, net lists) |
| `list_schematics` | Lists `.SchDoc` files in a folder |
| `search_component` | Finds components by designator, value, or description |
| `get_net_connections` | Shows which pins are connected to a given net |

### Example questions you can ask Copilot

- "What components are on the E-Stop Safety schematic?"
- "Which pins are connected to the 24VDC net?"
- "List all relay designators in the DUT 1 IO schematic"
- "What is the footprint for Rly301?"

## What you get

### JSON output

```json
{
  "metadata": {
    "filename": "E-Stop Safety Section.SchDoc",
    "parser_version": "0.1.0"
  },
  "components": [
    {
      "designator": "Rly202",
      "library_reference": "WAGO - Relay, 788-312",
      "description": "24V 2CO 8A Safety Relay and Base",
      "footprint": "",
      "value": "788-312",
      "parameters": {"Value": "788-312"},
      "pins": [
        {"designator": "A1", "name": "A1", "electrical": "Passive"},
        {"designator": "11", "name": "11", "electrical": "Passive"}
      ]
    }
  ],
  "nets": {
    "E-Stop 1(1)": ["Rly201.A1", "[Port]E-Stop 1(1)"],
    "E-Stop Rst (3)": ["Rly202.A2", "Rly202.14", "Rly203.14"]
  },
  "pins": [],
  "ports": [
    {"name": "E-Stop 1(1)", "io_type": "Bidirectional", "x": 100.0, "y": 200.0}
  ],
  "power_ports": [],
  "hierarchy": []
}
```

### Markdown output

The Markdown output contains:

- **Component table** with designator, library reference, value, footprint, and description
- **Power rails** (GND, VCC, etc.) with their symbol styles
- **Ports** (connections between schematic sheets)
- **Net list** showing which component pins are connected to each net
- **Pin map** listing every pin on every component
- **Sheet hierarchy** if the schematic references child sheets

## How it works

Altium `.SchDoc` files are OLE2 compound documents (the same container format as old `.doc` files). Inside, the `FileHeader` stream contains all schematic objects as length-prefixed, pipe-delimited key-value records.

Each record has a `RECORD` field that identifies its type:

| Record ID | Type | What it contains |
|-----------|------|------------------|
| 1 | Component | Library reference, description, part count |
| 2 | Pin | Name, designator, electrical type, position |
| 15 | Sheet Symbol | Child sheet reference |
| 16 | Sheet Entry | Port name and IO direction on a sheet symbol |
| 17 | Power Port | Named power rail (GND, VCC, etc.) |
| 18 | Port | Inter-sheet connection point |
| 25 | Net Label | Named net at a specific position |
| 27 | Wire | Coordinates of wire segments |
| 29 | Junction | Wire merge point |
| 34 | Designator | Component reference designator (R1, U3, etc.) |
| 41 | Parameter | Component parameters (value, comment, etc.) |
| 45 | Implementation | Footprint / model reference |

Child records (pins, designators, parameters) link to their parent component via `OWNERINDEX`, which is the 0-based position of the parent in the record stream (counting from records[1]).

Net connectivity is resolved by:
1. Collecting all wire segments and building a union-find graph on their endpoints
2. Calculating pin connection points from body position + pin length in the rotation direction
3. Snapping pins, net labels, power ports, and ports to the nearest wire endpoint (within ±2 units)
4. Grouping connected pins under the net name assigned by labels, power ports, or ports

## Limitations

- **Coordinate-based net resolution** — pins snap to wire endpoints within ±2 Altium units. Non-standard placements may cause missed connections.
- **Per-sheet only** — each `.SchDoc` is parsed independently. Cross-sheet net tracing (via the `.PrjPCB` project file) is not yet supported.
- **Data only** — no visual rendering. Use Altium 365 or Altium Designer to view the schematic graphically.
- **Tested with Altium Designer v20–v24** — older or newer versions may have undocumented record types.

## License

MIT — see [LICENSE](LICENSE).
