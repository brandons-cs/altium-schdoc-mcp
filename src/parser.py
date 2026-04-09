"""
Altium SchDoc binary parser.

Reads .SchDoc files (OLE2 compound documents) and extracts structured
schematic data: components, pins, nets, ports, hierarchy, and parameters.
"""

import struct
from pathlib import Path

import olefile


# Altium record type IDs
RECORD_COMPONENT = "1"
RECORD_PIN = "2"
RECORD_LABEL = "4"
RECORD_POLYLINE = "6"
RECORD_RECTANGLE = "14"
RECORD_SHEET_SYMBOL = "15"
RECORD_SHEET_ENTRY = "16"
RECORD_POWER_PORT = "17"
RECORD_PORT = "18"
RECORD_NO_ERC = "22"
RECORD_NET_LABEL = "25"
RECORD_BUS = "26"
RECORD_WIRE = "27"
RECORD_JUNCTION = "29"
RECORD_SHEET = "31"
RECORD_SHEET_NAME = "32"
RECORD_SHEET_FILENAME = "33"
RECORD_DESIGNATOR = "34"
RECORD_PARAMETER = "41"
RECORD_IMPL_LIST = "44"
RECORD_IMPLEMENTATION = "45"
RECORD_IMPL_PIN_ASSOC = "46"
RECORD_IMPL_PIN = "47"

# Pin electrical types
PIN_ELECTRICAL_TYPES = {
    "0": "Input",
    "1": "IO",
    "2": "Output",
    "3": "OpenCollector",
    "4": "Passive",
    "5": "HiZ",
    "6": "OpenEmitter",
    "7": "Power",
}

# Power port styles
POWER_PORT_STYLES = {
    "0": "Circle",
    "1": "Arrow",
    "2": "Bar",
    "3": "Wave",
    "4": "PowerGround",
    "5": "SignalGround",
    "6": "Earth",
    "7": "GostArrow",
    "8": "GostPowerGround",
    "9": "GostEarth",
    "10": "GostBar",
}

# Port IO types
PORT_IO_TYPES = {
    "0": "Unspecified",
    "1": "Output",
    "2": "Input",
    "3": "Bidirectional",
}


def _read_records(data: bytes) -> list[dict[str, str]]:
    """Parse the binary FileHeader stream into a list of key-value record dicts."""
    pos = 0
    records = []
    while pos < len(data):
        if pos + 4 > len(data):
            break
        length = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        if length == 0 or pos + length > len(data):
            break
        raw = data[pos : pos + length]
        pos += length
        text = raw.decode("latin-1").strip("\x00")
        pairs = {}
        for part in text.split("|"):
            if "=" in part:
                k, v = part.split("=", 1)
                pairs[k.upper()] = v
        if pairs:
            records.append(pairs)
    return records


def _build_owner_map(records: list[dict]) -> dict[int, list[int]]:
    """Build a map from owner ordinal -> list of child record indices.
    
    OWNERINDEX is 0-based, counting from records[1] onwards (records[0] is the
    file header, which is not addressable via OWNERINDEX).
    """
    owner_map: dict[int, list[int]] = {}
    for i, r in enumerate(records):
        oi = r.get("OWNERINDEX")
        if oi is not None:
            try:
                owner_ord = int(oi)
                owner_map.setdefault(owner_ord, []).append(i)
            except ValueError:
                pass
    return owner_map


def _get_children(records, owner_map, record_index):
    """Get child records for a record at the given index."""
    ordinal = record_index - 1  # convert to 0-based ordinal (skip header)
    return [records[i] for i in owner_map.get(ordinal, [])]


def _extract_wire_points(record: dict) -> list[tuple[float, float]]:
    """Extract wire endpoint coordinates from a wire record."""
    points = []
    count = int(record.get("LOCATIONCOUNT", "0"))
    for i in range(1, count + 1):
        x_key = f"X{i}"
        y_key = f"Y{i}"
        if x_key in record and y_key in record:
            x = float(record[x_key])
            y = float(record[y_key])
            points.append((x, y))
    return points


def _resolve_nets(records: list[dict], owner_map: dict) -> dict[str, list[str]]:
    """Resolve net connectivity by matching wire endpoints to pins, ports, net labels, and power ports.
    
    Strategy: build a coordinate → net_name map from net labels and power ports,
    then trace wires to connect pins to nets. Pins that share a wire endpoint
    with a named net get assigned to that net. Unnamed wire groups get auto-named.
    """
    TOLERANCE = 2  # coordinate matching tolerance (Altium units, ~1-2 for rounding)

    # Collect all positioned objects with net significance
    net_labels = []  # (x, y, net_name)
    power_ports = []  # (x, y, net_name)
    ports = []  # (x, y, net_name)
    pin_positions = []  # (x, y, component_desig, pin_desig)
    wire_segments = []  # [(x1,y1), (x2,y2), ...]
    junctions = []  # (x, y)

    # Build component designator lookup (ordinal -> designator text)
    comp_designators = {}
    for i, r in enumerate(records):
        if r.get("RECORD") == RECORD_COMPONENT:
            ordinal = i - 1
            for child_idx in owner_map.get(ordinal, []):
                child = records[child_idx]
                if child.get("RECORD") == RECORD_DESIGNATOR:
                    comp_designators[ordinal] = child.get("TEXT", "")
                    break

    for i, r in enumerate(records):
        rtype = r.get("RECORD", "")

        if rtype == RECORD_NET_LABEL:
            x = float(r.get("LOCATION.X", "0"))
            y = float(r.get("LOCATION.Y", "0"))
            net_labels.append((x, y, r.get("TEXT", "")))

        elif rtype == RECORD_POWER_PORT:
            x = float(r.get("LOCATION.X", "0"))
            y = float(r.get("LOCATION.Y", "0"))
            power_ports.append((x, y, r.get("TEXT", "")))

        elif rtype == RECORD_PORT:
            x = float(r.get("LOCATION.X", "0"))
            y = float(r.get("LOCATION.Y", "0"))
            ports.append((x, y, r.get("NAME", "")))

        elif rtype == RECORD_PIN:
            oi = r.get("OWNERINDEX")
            if oi is not None:
                try:
                    owner_ord = int(oi)
                    desig = comp_designators.get(owner_ord, "?")
                    pin_desig = r.get("DESIGNATOR", "")
                    # Pin LOCATION is the body-end. The connection (hot) point
                    # is at LOCATION + PINLENGTH in the direction of rotation.
                    # PINCONGLOMERATE bits 0-1: 0=right, 1=up, 2=left, 3=down
                    bx = float(r.get("LOCATION.X", "0"))
                    by = float(r.get("LOCATION.Y", "0"))
                    pin_len = float(r.get("PINLENGTH", "0"))
                    cong = int(r.get("PINCONGLOMERATE", "0"))
                    rotation = cong & 0x03
                    dx, dy = 0.0, 0.0
                    if rotation == 0:
                        dx = pin_len
                    elif rotation == 1:
                        dy = pin_len
                    elif rotation == 2:
                        dx = -pin_len
                    elif rotation == 3:
                        dy = -pin_len
                    x = bx + dx
                    y = by + dy
                    pin_positions.append((x, y, desig, pin_desig))
                except ValueError:
                    pass

        elif rtype == RECORD_WIRE:
            points = _extract_wire_points(r)
            if len(points) >= 2:
                wire_segments.append(points)

        elif rtype == RECORD_JUNCTION:
            x = float(r.get("LOCATION.X", "0"))
            y = float(r.get("LOCATION.Y", "0"))
            junctions.append((x, y))

    # Build connectivity graph: union-find on coordinate points
    # Each unique (x,y) position is a node. Wires connect their endpoints.
    point_to_id: dict[tuple[int, int], int] = {}
    parent: list[int] = []

    def _quantize(x, y):
        return (round(x), round(y))

    def _get_id(pt):
        if pt not in point_to_id:
            point_to_id[pt] = len(parent)
            parent.append(len(parent))
        return point_to_id[pt]

    def _find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def _union(a, b):
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[ra] = rb

    # Connect wire segments
    for points in wire_segments:
        ids = [_get_id(_quantize(p[0], p[1])) for p in points]
        for j in range(len(ids) - 1):
            _union(ids[j], ids[j + 1])

    # Connect junctions (they merge overlapping wire endpoints)
    for jx, jy in junctions:
        jpt = _quantize(jx, jy)
        if jpt in point_to_id:
            jid = point_to_id[jpt]
            # Junction at this point already connected via wires

    # Assign net names from labels and power ports
    # Use tolerance-based snapping for labels/ports/pins to wire endpoints
    def _snap_to_wire(x, y):
        """Find the nearest wire-graph point within TOLERANCE, or return None."""
        pt = _quantize(x, y)
        if pt in point_to_id:
            return pt
        # Search nearby quantized points
        qx, qy = round(x), round(y)
        for dx in range(-TOLERANCE, TOLERANCE + 1):
            for dy in range(-TOLERANCE, TOLERANCE + 1):
                candidate = (qx + dx, qy + dy)
                if candidate in point_to_id:
                    return candidate
        return None

    group_names: dict[int, str] = {}
    for x, y, name in net_labels + power_ports + ports:
        snapped = _snap_to_wire(x, y)
        if snapped is not None:
            root = _find(point_to_id[snapped])
            if name:
                group_names[root] = name

    # Map pins to nets
    nets: dict[str, list[str]] = {}
    unnamed_counter = 0
    for x, y, comp_desig, pin_desig in pin_positions:
        snapped = _snap_to_wire(x, y)
        if snapped is not None:
            root = _find(point_to_id[snapped])
            net_name = group_names.get(root)
            if not net_name:
                unnamed_counter += 1
                net_name = f"Net_{unnamed_counter}"
                group_names[root] = net_name
            pin_ref = f"{comp_desig}.{pin_desig}" if comp_desig and pin_desig else None
            if pin_ref and net_name:
                nets.setdefault(net_name, []).append(pin_ref)

    # Also add ports to their nets (they represent inter-sheet connections)
    for x, y, name in ports:
        snapped = _snap_to_wire(x, y)
        if snapped is not None:
            root = _find(point_to_id[snapped])
            net_name = group_names.get(root, name)
            if name and net_name:
                pin_ref = f"[Port]{name}"
                nets.setdefault(net_name, []).append(pin_ref)

    return dict(sorted(nets.items()))


def parse_schdoc(file_path: str | Path) -> dict:
    """Parse an Altium .SchDoc file and return structured data.
    
    Args:
        file_path: Path to the .SchDoc file.
        
    Returns:
        Dictionary with keys: metadata, components, nets, pins, hierarchy, ports.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ole = olefile.OleFileIO(str(file_path))
    try:
        data = ole.openstream("FileHeader").read()
    finally:
        ole.close()

    records = _read_records(data)
    owner_map = _build_owner_map(records)

    # --- Metadata ---
    metadata = {
        "filename": file_path.name,
        "parser_version": "0.1.0",
    }
    for r in records:
        if r.get("RECORD") == RECORD_SHEET:
            metadata["sheet_style"] = r.get("SHEETSTYLE", "")
            break

    # --- Components ---
    components = []
    for i, r in enumerate(records):
        if r.get("RECORD") != RECORD_COMPONENT:
            continue

        ordinal = i - 1
        children = [records[ci] for ci in owner_map.get(ordinal, [])]

        designator = ""
        footprint = ""
        pins = []
        params = {}

        for child in children:
            ct = child.get("RECORD", "")
            if ct == RECORD_DESIGNATOR:
                designator = child.get("TEXT", "")
            elif ct == RECORD_PIN:
                pin_info = {
                    "designator": child.get("DESIGNATOR", ""),
                    "name": child.get("NAME", ""),
                    "electrical": PIN_ELECTRICAL_TYPES.get(
                        child.get("ELECTRICAL", ""), child.get("ELECTRICAL", "")
                    ),
                }
                pins.append(pin_info)
            elif ct == RECORD_IMPLEMENTATION and child.get("ISCURRENT") == "T":
                footprint = child.get("MODELNAME", "")
            elif ct == RECORD_PARAMETER:
                name = child.get("NAME", "")
                text = child.get("TEXT", "")
                if name and text and child.get("ISHIDDEN") != "T":
                    params[name] = text

        components.append({
            "designator": designator,
            "library_reference": r.get("LIBREFERENCE", ""),
            "description": r.get("COMPONENTDESCRIPTION", ""),
            "footprint": footprint,
            "value": params.get("Value", params.get("Comment", "")),
            "parameters": params,
            "pins": sorted(pins, key=lambda p: p["designator"]),
        })

    components.sort(key=lambda c: _natural_sort_key(c["designator"]))

    # --- Nets ---
    nets = _resolve_nets(records, owner_map)

    # --- Ports (inter-sheet connections) ---
    ports_list = []
    for r in records:
        if r.get("RECORD") == RECORD_PORT:
            ports_list.append({
                "name": r.get("NAME", ""),
                "io_type": PORT_IO_TYPES.get(r.get("IOTYPE", ""), r.get("IOTYPE", "")),
                "x": float(r.get("LOCATION.X", "0")),
                "y": float(r.get("LOCATION.Y", "0")),
            })
    ports_list.sort(key=lambda p: p["name"])

    # --- Power Ports ---
    power_ports_list = []
    seen_power = set()
    for r in records:
        if r.get("RECORD") == RECORD_POWER_PORT:
            text = r.get("TEXT", "")
            if text and text not in seen_power:
                seen_power.add(text)
                power_ports_list.append({
                    "name": text,
                    "style": POWER_PORT_STYLES.get(r.get("STYLE", ""), r.get("STYLE", "")),
                })
    power_ports_list.sort(key=lambda p: p["name"])

    # --- Hierarchy (Sheet Symbols + Sheet Entries) ---
    hierarchy = []
    for i, r in enumerate(records):
        if r.get("RECORD") == RECORD_SHEET_SYMBOL:
            ordinal = i - 1
            children = [records[ci] for ci in owner_map.get(ordinal, [])]
            
            sheet_name = ""
            sheet_filename = ""
            entries = []
            
            for child in children:
                ct = child.get("RECORD", "")
                if ct == RECORD_SHEET_NAME:
                    sheet_name = child.get("TEXT", "")
                elif ct == RECORD_SHEET_FILENAME:
                    sheet_filename = child.get("TEXT", "")
                elif ct == RECORD_SHEET_ENTRY:
                    entries.append({
                        "name": child.get("NAME", ""),
                        "io_type": PORT_IO_TYPES.get(
                            child.get("IOTYPE", ""), child.get("IOTYPE", "")
                        ),
                    })

            hierarchy.append({
                "sheet_name": sheet_name,
                "sheet_filename": sheet_filename,
                "entries": sorted(entries, key=lambda e: e["name"]),
            })

    # --- All pins flat list for easy lookup ---
    all_pins = []
    for comp in components:
        for pin in comp["pins"]:
            all_pins.append({
                "component": comp["designator"],
                "pin_designator": pin["designator"],
                "pin_name": pin["name"],
                "electrical": pin["electrical"],
            })

    return {
        "metadata": metadata,
        "components": components,
        "nets": nets,
        "pins": all_pins,
        "ports": ports_list,
        "power_ports": power_ports_list,
        "hierarchy": hierarchy,
    }


def _natural_sort_key(s: str):
    """Sort key for natural ordering: R1, R2, R10 instead of R1, R10, R2."""
    import re
    parts = re.split(r"(\d+)", s)
    result = []
    for part in parts:
        if part.isdigit():
            result.append((0, int(part)))
        else:
            result.append((1, part.lower()))
    return result
