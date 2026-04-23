"""
UAsset parser for Motor Town .uasset files.
Extracts name table, import table, and preserves raw bytes for lossless round-trip.
"""
import struct
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class NameEntry:
    text: str
    hash_bytes: bytes  # 4-byte hash preserved for round-trip


@dataclass
class ImportEntry:
    """Simplified import entry - we preserve raw bytes but extract key info."""
    raw_bytes: bytes
    class_package: int  # name index
    class_name: int     # name index
    outer_index: int
    object_name: int    # name index


@dataclass
class UAssetFile:
    """Parsed .uasset file with all data needed for viewing and round-trip writing."""
    raw_bytes: bytes
    file_path: str
    names: List[NameEntry] = field(default_factory=list)
    imports: List[ImportEntry] = field(default_factory=list)

    # Key metadata extracted from parsing
    class_type: str = ""          # e.g. "MHEngineDataAsset"
    asset_name: str = ""          # e.g. "lexusV10"
    asset_path: str = ""          # e.g. "/Game/Cars/Parts/Engine/lexusV10"

    # References found in name table
    torque_curve_name: str = ""   # e.g. "TorqueCurve_V12"
    sound_refs: List[str] = field(default_factory=list)

    def get_name(self, index: int) -> str:
        """Get name by index. Handles negative indices (import refs)."""
        if 0 <= index < len(self.names):
            return self.names[index].text
        return f"[index:{index}]"

    def get_import_object_name(self, neg_index: int) -> str:
        """Get import object name from negative index (e.g., -2 -> imports[1])."""
        # UE uses 1-based negative indexing: -1 = imports[0], -2 = imports[1], etc.
        actual_idx = (-neg_index) - 1
        if 0 <= actual_idx < len(self.imports):
            name_idx = self.imports[actual_idx].object_name
            return self.get_name(name_idx)
        return f"[import:{neg_index}]"


def parse_uasset(file_path: str) -> UAssetFile:
    """Parse a .uasset file and extract name table and import table."""
    with open(file_path, 'rb') as f:
        raw = f.read()

    asset = UAssetFile(raw_bytes=raw, file_path=file_path)

    # Extract all readable strings and classify them
    _extract_strings(asset, raw)

    # Try to determine class type and asset name from strings
    _classify_asset(asset)

    return asset


def _extract_strings(asset: UAssetFile, data: bytes):
    """Extract length-prefixed strings from the name table area of the .uasset."""
    names = []
    i = 0
    while i < len(data) - 8:
        # Try reading as a length-prefixed string (UE format: int32 length, then chars, then null, then 4-byte hash)
        slen = struct.unpack_from('<i', data, i)[0]
        if 2 <= slen <= 200:
            end = i + 4 + slen
            if end + 4 <= len(data):
                try:
                    # Check for null terminator at expected position
                    if data[end - 1] == 0:
                        text = data[i + 4:end - 1].decode('ascii')
                        if all(c.isprintable() or c in '\t\n\r' for c in text) and len(text) >= 1:
                            hash_bytes = data[end:end + 4]
                            names.append(NameEntry(text=text, hash_bytes=hash_bytes))
                            i = end + 4
                            continue
                except (UnicodeDecodeError, ValueError):
                    pass
        i += 1

    asset.names = names


def _classify_asset(asset: UAssetFile):
    """Determine asset type, name, and references from extracted strings."""
    for entry in asset.names:
        t = entry.text

        # Class type detection
        if t == 'MHEngineDataAsset':
            asset.class_type = 'Engine'
        elif t == 'MTTransmissionDataAsset':
            asset.class_type = 'Transmission'
        elif t == 'MTTirePhysicsDataAsset':
            asset.class_type = 'Tire'
        elif t == 'MTLSDDataAsset':
            asset.class_type = 'LSD'
        elif t == 'CurveFloat' and not asset.class_type:
            asset.class_type = 'TorqueCurve'

        # Asset path
        if t.startswith('/Game/Cars/Parts/'):
            if not asset.asset_path or len(t) < len(asset.asset_path):
                asset.asset_path = t

        # Torque curve reference
        if t.startswith('TorqueCurve_'):
            asset.torque_curve_name = t

        # Sound references
        if t.startswith('SC_'):
            asset.sound_refs.append(t)

    # Extract asset name from path
    if asset.asset_path:
        asset.asset_name = asset.asset_path.rsplit('/', 1)[-1]

    # Fallback: look for the Default__ pattern
    if not asset.asset_name:
        for entry in asset.names:
            if entry.text.startswith('Default__'):
                continue
            if not entry.text.startswith('/') and not entry.text.startswith('SC_') \
               and entry.text not in ('Class', 'Package', 'SoundCue', 'CurveFloat',
                                       'MHEngineDataAsset', 'MTTransmissionDataAsset',
                                       'MTTirePhysicsDataAsset', 'MTLSDDataAsset'):
                if len(entry.text) > 2 and not entry.text.startswith('TorqueCurve_'):
                    asset.asset_name = entry.text
                    break
