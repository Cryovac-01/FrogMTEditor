from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import wave
import audioop
from pathlib import Path
from typing import Any, Dict, List, Optional

from parsers.uasset_clone import (
    _build_name_entry,
    _cityhash_lite,
    _parse_name_table,
    _read_fstring,
    _write_fstring,
)
from template_engines import load_template_specs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VANILLA_SOUND_BASE = PROJECT_ROOT / 'data' / 'vanilla' / 'Engine' / 'Sound'
MOD_SOUND_BASE = PROJECT_ROOT / 'data' / 'mod' / 'MotorTown' / 'Content' / 'Cars' / 'Parts' / 'Engine' / 'Sound'
AUDIO_WORKSPACE_ROOT = PROJECT_ROOT / 'data' / 'audio'
ENGINE_AUDIO_WORKSPACE = AUDIO_WORKSPACE_ROOT / 'engines'
ENGINE_AUDIO_MANIFEST_PATH = AUDIO_WORKSPACE_ROOT / 'engine_audio_manifest.json'
ENGINE_AUDIO_OVERRIDE_PATH = AUDIO_WORKSPACE_ROOT / 'engine_sound_overrides.json'
ENGINE_AUDIO_NORMALIZATION_MANIFEST_PATH = AUDIO_WORKSPACE_ROOT / 'engine_audio_normalization_manifest.json'
ENGINE_AUDIO_RESEARCH_PATH = AUDIO_WORKSPACE_ROOT / 'research'
ENGINE_AUDIO_TOOLCHAIN_PATH = AUDIO_WORKSPACE_ROOT / 'engine_audio_toolchain.json'
ENGINE_AUDIO_SOURCE_SHORTLIST_PATH = ENGINE_AUDIO_RESEARCH_PATH / 'engine_audio_source_shortlist.json'
ENGINE_AUDIO_ENCODED_MANIFEST_NAME = 'encoded_manifest.json'
UNREAL_AUDIO_PROJECT_NAME = 'FrogAudioCook'
UNREAL_AUDIO_PROJECT_ROOT = AUDIO_WORKSPACE_ROOT / 'unreal_project' / UNREAL_AUDIO_PROJECT_NAME
UNREAL_AUDIO_UPROJECT_PATH = UNREAL_AUDIO_PROJECT_ROOT / f'{UNREAL_AUDIO_PROJECT_NAME}.uproject'
UNREAL_AUDIO_JOB_ROOT = AUDIO_WORKSPACE_ROOT / 'unreal_jobs'
UNREAL_AUDIO_SCRIPT_PATH = PROJECT_ROOT / 'scripts' / 'unreal_import_engine_audio_assets.py'
UNREAL_AUDIO_CONTENT_ROOT = '/Game/EngineAudioImports'
UNREAL_AUDIO_DDC_DIRNAME = 'ProjectDerivedData'

_SOUND_PREFIX = '/Game/Cars/Parts/Engine/Sound/'
_SKIP_HEADS = frozenset({'Backfire', 'Intake', 'jake', 'Starter'})
_RPM_PATTERNS = (
    re.compile(r'(?P<rpm>\d{3,5})rpm', re.IGNORECASE),
    re.compile(r'_(?P<rpm>\d)_(?P<thousands>\d{3})'),
    re.compile(r'(?P<rpm>\d)k', re.IGNORECASE),
)
_FADE_MS_DEFAULT = 30
_TARGET_SAMPLE_RATE_DEFAULT = 48000
_TARGET_SAMPLE_WIDTH_DEFAULT = 2
_TARGET_CHANNELS_DEFAULT = 2
_ENGINE_SAMPLE_DURATION_HINTS = (
    (0, 6.0),
    (1000, 5.5),
    (2000, 5.0),
    (4000, 4.5),
    (7000, 4.0),
)


def _discover_epic_unreal_roots() -> List[Path]:
    roots: List[Path] = []
    seen: set[str] = set()

    def _add_root(candidate: Path) -> None:
        key = str(candidate).lower()
        if key in seen:
            return
        seen.add(key)
        roots.append(candidate)

    launcher_manifest = Path(r'C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat')
    if launcher_manifest.is_file():
        try:
            payload = json.loads(launcher_manifest.read_text(encoding='utf-8'))
        except Exception:
            payload = {}
        for row in payload.get('InstallationList', []):
            app_name = str(row.get('AppName') or '').strip()
            install_location = str(row.get('InstallLocation') or '').strip()
            if not app_name.startswith('UE_') or not install_location:
                continue
            _add_root(Path(install_location) / 'Engine' / 'Binaries' / 'Win64')

    for base_dir in (
        Path(r'C:\Program Files\Epic Games'),
        Path(r'C:\Program Files (x86)\Epic Games'),
    ):
        if not base_dir.is_dir():
            continue
        for child in sorted(base_dir.glob('UE_*')):
            _add_root(child / 'Engine' / 'Binaries' / 'Win64')

    return roots


def _asset_path_from_uasset_file(uasset_path: Path) -> str:
    with uasset_path.open('rb') as f:
        data = f.read()
    folder_text, _folder_bytes = _read_fstring(data, 32)
    return folder_text


def _sound_index_aliases(uasset_path: Path, sound_root: Path) -> List[str]:
    aliases: List[str] = []
    if uasset_path.parent != sound_root / 'Bike':
        return aliases
    try:
        for ref in extract_engine_sound_paths(uasset_path):
            if not ref.startswith(_SOUND_PREFIX + 'Bike/'):
                continue
            parts = ref[len(_SOUND_PREFIX):].split('/')
            if len(parts) == 2:
                aliases.append(ref)
    except Exception:
        return aliases
    return aliases


def build_sound_asset_index(sound_root: Path = VANILLA_SOUND_BASE) -> Dict[str, Path]:
    index: Dict[str, Path] = {}
    if not sound_root.is_dir():
        return index
    for path in sorted(sound_root.rglob('*.uasset')):
        try:
            asset_path = _asset_path_from_uasset_file(path)
        except Exception:
            continue
        if not asset_path.startswith(_SOUND_PREFIX):
            continue
        index[asset_path] = path
        for alias in _sound_index_aliases(path, sound_root):
            index.setdefault(alias, path)
    return index


def _extract_name_entries(uasset_path: Path) -> List[Dict[str, Any]]:
    with uasset_path.open('rb') as f:
        data = f.read()
    folder_text, folder_bytes = _read_fstring(data, 32)
    folder_end = 32 + folder_bytes
    name_count = struct.unpack_from('<i', data, folder_end + 4)[0]
    name_offset = struct.unpack_from('<i', data, folder_end + 8)[0]
    entries, _ = _parse_name_table(data, name_offset, name_count)
    return entries


def extract_engine_sound_paths(uasset_path: Path) -> List[str]:
    seen: set[str] = set()
    paths: List[str] = []
    for entry in _extract_name_entries(uasset_path):
        text = entry.get('text', '')
        if not text.startswith(_SOUND_PREFIX):
            continue
        suffix = text[len(_SOUND_PREFIX):]
        parts = suffix.split('/')
        if not parts:
            continue
        if parts[0] in _SKIP_HEADS:
            continue
        if parts[0] == 'Bike' and len(parts) >= 2 and parts[1] in _SKIP_HEADS:
            continue
        if text in seen:
            continue
        seen.add(text)
        paths.append(text)
    return paths


def primary_engine_sound_path(uasset_path: Path) -> Optional[str]:
    paths = extract_engine_sound_paths(uasset_path)
    return paths[0] if paths else None


def sound_dir_token_from_asset_path(asset_path: str) -> Optional[str]:
    if not asset_path.startswith(_SOUND_PREFIX):
        return None
    suffix = asset_path[len(_SOUND_PREFIX):]
    parts = suffix.split('/')
    if not parts:
        return None
    if parts[0] == 'Bike':
        return parts[1] if len(parts) >= 2 else None
    return parts[0]


def rewrite_sound_asset_path(asset_path: str, override_sound_dir: str) -> str:
    if not asset_path.startswith(_SOUND_PREFIX):
        return asset_path
    suffix = asset_path[len(_SOUND_PREFIX):]
    parts = suffix.split('/')
    if not parts:
        return asset_path
    if parts[0] == 'Bike':
        if len(parts) < 2:
            return asset_path
        parts[1] = override_sound_dir
    else:
        parts[0] = override_sound_dir
    return _SOUND_PREFIX + '/'.join(parts)


def asset_path_to_output_file(sound_root: Path, asset_path: str) -> Path:
    suffix = asset_path[len(_SOUND_PREFIX):]
    return sound_root.joinpath(*suffix.split('/')).with_suffix('.uasset')


def resolve_sound_asset_file(asset_path: str, asset_index: Optional[Dict[str, Path]] = None,
                             sound_root: Path = VANILLA_SOUND_BASE) -> Path:
    if asset_index and asset_path in asset_index:
        return asset_index[asset_path]
    candidate = asset_path_to_output_file(sound_root, asset_path)
    if candidate.is_file():
        return candidate
    if asset_path.startswith(_SOUND_PREFIX + 'Bike/'):
        bike_dir = sound_root / 'Bike'
        if bike_dir.is_dir():
            for root_uasset in bike_dir.glob('*.uasset'):
                try:
                    refs = extract_engine_sound_paths(root_uasset)
                except Exception:
                    continue
                if asset_path in refs:
                    return root_uasset
    raise KeyError(asset_path)


def _ordered_unique(items: List[str]) -> List[str]:
    ordered: List[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _copy_optional_sidecar(src_uasset: Path, dst_uasset: Path, suffix: str) -> None:
    src = src_uasset.with_suffix(suffix)
    if not src.is_file():
        return
    dst = dst_uasset.with_suffix(suffix)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _require_sidecar(src_uasset: Path, suffix: str) -> Path:
    src = src_uasset.with_suffix(suffix)
    if not src.is_file():
        raise FileNotFoundError(f'Missing sidecar for {src_uasset.name}: {src.name}')
    return src


def clone_uasset_to_new_asset_path(template_path: Path, output_path: Path, new_asset_path: str) -> None:
    data = template_path.read_bytes()
    fixed_header = data[:28]
    old_total_size = struct.unpack_from('<i', data, 28)[0]

    folder_text, folder_bytes = _read_fstring(data, 32)
    folder_end = 32 + folder_bytes
    old_name = folder_text.rsplit('/', 1)[-1]
    new_name = new_asset_path.rsplit('/', 1)[-1]

    name_count = struct.unpack_from('<i', data, folder_end + 4)[0]
    name_offset = struct.unpack_from('<i', data, folder_end + 8)[0]
    header_fields = bytearray(data[folder_end:name_offset])
    name_entries, name_table_size = _parse_name_table(data, name_offset, name_count)
    rest_start = name_offset + name_table_size
    rest_data = data[rest_start:]

    for entry in name_entries:
        text = entry['text']
        new_text = text
        if text == folder_text:
            new_text = new_asset_path
        elif text == old_name and old_name != new_name:
            new_text = new_name
        elif text == f'Default__{old_name}' and old_name != new_name:
            new_text = f'Default__{new_name}'
        if new_text != text:
            entry['text'] = new_text
            entry['hash'] = _cityhash_lite(new_text)

    new_folder_bytes = _write_fstring(new_asset_path)
    new_name_table = b''.join(_build_name_entry(entry['text'], entry['hash']) for entry in name_entries)

    folder_delta = len(new_folder_bytes) - folder_bytes
    name_table_delta = len(new_name_table) - name_table_size
    total_delta = folder_delta + name_table_delta

    orig_export_count = struct.unpack_from('<i', header_fields, 28)[0]
    orig_export_offset = struct.unpack_from('<i', header_fields, 32)[0]
    orig_depends_offset = struct.unpack_from('<i', header_fields, 44)[0]

    new_name_offset = name_offset + folder_delta
    struct.pack_into('<i', header_fields, 8, new_name_offset)

    old_serial_size = 0
    eo_tmp = struct.unpack_from('<i', header_fields, 32)[0]
    if eo_tmp > 0 and eo_tmp < len(data):
        old_serial_size = struct.unpack_from('<q', data, eo_tmp + 28)[0]
    upper_bound = old_total_size + max(old_serial_size, 0)
    for byte_off in range(0, len(header_fields) - 3, 4):
        val = struct.unpack_from('<i', header_fields, byte_off)[0]
        if rest_start <= val <= upper_bound:
            struct.pack_into('<i', header_fields, byte_off, val + total_delta)

    gen_name_off = 22 * 4
    if gen_name_off + 4 <= len(header_fields):
        old_gen = struct.unpack_from('<i', header_fields, gen_name_off)[0]
        if old_gen == name_count:
            struct.pack_into('<i', header_fields, gen_name_off, name_count)

    new_total_size = old_total_size + total_delta

    if total_delta != 0 and orig_export_count > 0 and orig_export_offset > 0:
        rest_bytes = bytearray(rest_data)
        if orig_depends_offset > orig_export_offset and orig_export_count > 0:
            entry_size = (orig_depends_offset - orig_export_offset) // orig_export_count
        else:
            entry_size = 96
        for i in range(orig_export_count):
            serial_off_pos = (orig_export_offset - rest_start) + i * entry_size + 36
            if 0 <= serial_off_pos and serial_off_pos + 8 <= len(rest_bytes):
                old_serial = struct.unpack_from('<q', rest_bytes, serial_off_pos)[0]
                struct.pack_into('<q', rest_bytes, serial_off_pos, old_serial + total_delta)
        rest_data = bytes(rest_bytes)

    result = bytearray()
    result += fixed_header
    result += struct.pack('<i', new_total_size)
    result += new_folder_bytes
    result += header_fields
    result += new_name_table
    result += rest_data

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(result)


def clone_uasset_with_path_map(template_path: Path, output_path: Path, new_asset_path: str,
                               exact_replacements: Optional[Dict[str, str]] = None) -> None:
    data = template_path.read_bytes()
    fixed_header = data[:28]
    old_total_size = struct.unpack_from('<i', data, 28)[0]

    folder_text, folder_bytes = _read_fstring(data, 32)
    folder_end = 32 + folder_bytes
    old_name = folder_text.rsplit('/', 1)[-1]
    new_name = new_asset_path.rsplit('/', 1)[-1]

    name_count = struct.unpack_from('<i', data, folder_end + 4)[0]
    name_offset = struct.unpack_from('<i', data, folder_end + 8)[0]
    header_fields = bytearray(data[folder_end:name_offset])
    name_entries, name_table_size = _parse_name_table(data, name_offset, name_count)
    rest_start = name_offset + name_table_size
    rest_data = data[rest_start:]

    replacements = dict(exact_replacements or {})
    replacements[folder_text] = new_asset_path
    object_replacements: Dict[str, str] = {}
    for src_path, dst_path in replacements.items():
        if not src_path.startswith(_SOUND_PREFIX) or not dst_path.startswith(_SOUND_PREFIX):
            continue
        old_obj = src_path.rsplit('/', 1)[-1]
        new_obj = dst_path.rsplit('/', 1)[-1]
        if old_obj and new_obj and old_obj != new_obj:
            object_replacements[old_obj] = new_obj

    for entry in name_entries:
        text = entry['text']
        new_text = replacements.get(text, text)
        if new_text == text:
            if text == old_name and old_name != new_name:
                new_text = new_name
            elif text == f'Default__{old_name}' and old_name != new_name:
                new_text = f'Default__{new_name}'
            elif '/' not in text and text in object_replacements:
                new_text = object_replacements[text]
        if new_text != text:
            entry['text'] = new_text
            entry['hash'] = _cityhash_lite(new_text)

    new_folder_bytes = _write_fstring(new_asset_path)
    new_name_table = b''.join(_build_name_entry(entry['text'], entry['hash']) for entry in name_entries)

    folder_delta = len(new_folder_bytes) - folder_bytes
    name_table_delta = len(new_name_table) - name_table_size
    total_delta = folder_delta + name_table_delta

    orig_export_count = struct.unpack_from('<i', header_fields, 28)[0]
    orig_export_offset = struct.unpack_from('<i', header_fields, 32)[0]
    orig_depends_offset = struct.unpack_from('<i', header_fields, 44)[0]

    new_name_offset = name_offset + folder_delta
    struct.pack_into('<i', header_fields, 8, new_name_offset)

    old_serial_size = 0
    eo_tmp = struct.unpack_from('<i', header_fields, 32)[0]
    if eo_tmp > 0 and eo_tmp < len(data):
        old_serial_size = struct.unpack_from('<q', data, eo_tmp + 28)[0]
    upper_bound = old_total_size + max(old_serial_size, 0)
    for byte_off in range(0, len(header_fields) - 3, 4):
        val = struct.unpack_from('<i', header_fields, byte_off)[0]
        if rest_start <= val <= upper_bound:
            struct.pack_into('<i', header_fields, byte_off, val + total_delta)

    gen_name_off = 22 * 4
    if gen_name_off + 4 <= len(header_fields):
        old_gen = struct.unpack_from('<i', header_fields, gen_name_off)[0]
        if old_gen == name_count:
            struct.pack_into('<i', header_fields, gen_name_off, name_count)

    new_total_size = old_total_size + total_delta

    if total_delta != 0 and orig_export_count > 0 and orig_export_offset > 0:
        rest_bytes = bytearray(rest_data)
        if orig_depends_offset > orig_export_offset and orig_export_count > 0:
            entry_size = (orig_depends_offset - orig_export_offset) // orig_export_count
        else:
            entry_size = 96
        for i in range(orig_export_count):
            serial_off_pos = (orig_export_offset - rest_start) + i * entry_size + 36
            if 0 <= serial_off_pos and serial_off_pos + 8 <= len(rest_bytes):
                old_serial = struct.unpack_from('<q', rest_bytes, serial_off_pos)[0]
                struct.pack_into('<q', rest_bytes, serial_off_pos, old_serial + total_delta)
        rest_data = bytes(rest_bytes)

    result = bytearray()
    result += fixed_header
    result += struct.pack('<i', new_total_size)
    result += new_folder_bytes
    result += header_fields
    result += new_name_table
    result += rest_data

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(result)


def _family_wave_files(root_asset_file: Path) -> List[Path]:
    family_files: List[Path] = []
    family_dir = root_asset_file.parent
    root_stem = root_asset_file.stem

    for path in sorted(family_dir.glob('*.uasset')):
        if path == root_asset_file:
            continue
        stem = path.stem
        if stem.startswith('SC_'):
            continue
        if stem == 'EngineSoundData' or stem.endswith('_EngineSoundData'):
            continue
        family_files.append(path)

    nested_dir = family_dir / root_stem
    if nested_dir.is_dir():
        for path in sorted(nested_dir.glob('*.uasset')):
            family_files.append(path)

    deduped: List[Path] = []
    seen: set[Path] = set()
    for path in family_files:
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return deduped


def _sound_family_asset_paths(root_asset_path: str, asset_index: Dict[str, Path]) -> List[str]:
    root_asset_file = resolve_sound_asset_file(root_asset_path, asset_index)
    root_self_path = _asset_path_from_uasset_file(root_asset_file)
    refs = extract_engine_sound_paths(root_asset_file)
    return _ordered_unique([root_self_path, root_asset_path, *refs])


def _rpm_value_from_name(name: str) -> Optional[int]:
    lower = name.lower()
    for pattern in _RPM_PATTERNS:
        match = pattern.search(lower)
        if not match:
            continue
        if 'thousands' in match.groupdict():
            return int(match.group('rpm') + match.group('thousands'))
        value = int(match.group('rpm'))
        if lower.endswith('k') or match.group(0).lower().endswith('k'):
            return value * 1000
        return value
    if 'idle' in lower:
        return 0
    return None


def recommended_sample_duration_seconds(name: str, rpm: Optional[int] = None) -> float:
    rpm_value = rpm if rpm is not None else _rpm_value_from_name(name)
    if rpm_value is None:
        return 4.5
    for threshold, duration in reversed(_ENGINE_SAMPLE_DURATION_HINTS):
        if rpm_value >= threshold:
            return duration
    return 4.5


def inspect_wav_file(path: Path) -> Dict[str, Any]:
    with wave.open(str(path), 'rb') as wav:
        params = wav.getparams()
        frame_count = wav.getnframes()
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        duration = frame_count / sample_rate if sample_rate else 0.0
        return {
            'path': str(path),
            'channels': channels,
            'sample_rate': sample_rate,
            'sample_width': sample_width,
            'frame_count': frame_count,
            'duration_seconds': round(duration, 6),
            'comptype': params.comptype,
            'compname': params.compname,
        }


def derive_pitch_shifted_wav_variant(
    src_path: Path,
    dst_path: Path,
    *,
    pitch_factor: float,
    gain: float = 1.0,
    fade_ms: int = _FADE_MS_DEFAULT,
) -> Dict[str, Any]:
    if pitch_factor <= 0:
        raise ValueError(f'pitch_factor must be > 0, got {pitch_factor}')
    if gain <= 0:
        raise ValueError(f'gain must be > 0, got {gain}')

    with wave.open(str(src_path), 'rb') as wav:
        params = wav.getparams()
        if params.comptype not in ('NONE', ''):
            raise ValueError(f'{src_path} is compressed and cannot be derived with stdlib wave')
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        source_frames = wav.getnframes()
        raw = wav.readframes(source_frames)

    if not raw:
        raise ValueError(f'{src_path} does not contain PCM data')

    derived_rate = max(1, int(round(sample_rate / pitch_factor)))
    shifted, _state = audioop.ratecv(raw, sample_width, channels, sample_rate, derived_rate, None)
    if gain != 1.0:
        shifted = audioop.mul(shifted, sample_width, gain)
    shifted = _apply_linear_fade(shifted, channels, sample_width, sample_rate, fade_in_ms=fade_ms, fade_out_ms=fade_ms)

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dst_path), 'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(shifted)

    output_frames = _pcm_frame_count(shifted, channels, sample_width)
    return {
        'source_file': str(src_path),
        'output_file': str(dst_path),
        'source_frame_count': source_frames,
        'source_duration_seconds': round(source_frames / sample_rate if sample_rate else 0.0, 6),
        'output_frame_count': output_frames,
        'output_duration_seconds': round(output_frames / sample_rate if sample_rate else 0.0, 6),
        'channels': channels,
        'sample_width': sample_width,
        'sample_rate': sample_rate,
        'pitch_factor': pitch_factor,
        'gain': gain,
        'fade_ms': fade_ms,
        'peak_after': audioop.max(shifted, sample_width) if shifted else 0,
        'rms_after': audioop.rms(shifted, sample_width) if shifted else 0,
    }


def _pcm_frame_count(data: bytes, channels: int, sample_width: int) -> int:
    frame_size = max(channels * sample_width, 1)
    return len(data) // frame_size


def _slice_pcm_frames(data: bytes, channels: int, sample_width: int, start_frame: int, end_frame: int) -> bytes:
    frame_size = channels * sample_width
    return data[start_frame * frame_size:end_frame * frame_size]


def _scale_pcm_segment(data: bytes, sample_width: int, scale: float) -> bytes:
    if not data or scale == 1.0:
        return data
    return audioop.mul(data, sample_width, scale)


def _pcm_peak_ceiling(sample_width: int) -> float:
    bits = max(int(sample_width) * 8, 1)
    if bits <= 8:
        return 127.0
    return float((1 << (bits - 1)) - 1)


def _apply_linear_fade(data: bytes, channels: int, sample_width: int, sample_rate: int,
                       fade_in_ms: int = 0, fade_out_ms: int = 0) -> bytes:
    if not data:
        return data
    frame_size = channels * sample_width
    total_frames = len(data) // frame_size
    if total_frames <= 0:
        return data

    def _fade_block(block: bytes, fade_in: bool) -> bytes:
        frame_count = len(block) // frame_size
        if frame_count <= 0:
            return b''
        if frame_count == 1:
            return _scale_pcm_segment(block, sample_width, 0.0)
        chunk = bytearray()
        denominator = max(frame_count - 1, 1)
        for idx in range(frame_count):
            if fade_in:
                factor = idx / denominator
            else:
                factor = (frame_count - 1 - idx) / denominator
            start = idx * frame_size
            end = start + frame_size
            chunk += _scale_pcm_segment(block[start:end], sample_width, factor)
        return bytes(chunk)

    fade_in_frames = min(total_frames, int(sample_rate * fade_in_ms / 1000))
    fade_out_frames = min(total_frames, int(sample_rate * fade_out_ms / 1000))
    overlap = fade_in_frames + fade_out_frames - total_frames
    if overlap > 0:
        trim = (overlap + 1) // 2
        fade_in_frames = max(0, fade_in_frames - trim)
        fade_out_frames = max(0, fade_out_frames - (overlap - trim))

    body_start = fade_in_frames
    body_end = total_frames - fade_out_frames
    result = bytearray()

    if fade_in_frames:
        head = _slice_pcm_frames(data, channels, sample_width, 0, fade_in_frames)
        result += _fade_block(head, True)
    if body_end > body_start:
        result += _slice_pcm_frames(data, channels, sample_width, body_start, body_end)
    if fade_out_frames:
        tail = _slice_pcm_frames(data, channels, sample_width, total_frames - fade_out_frames, total_frames)
        result += _fade_block(tail, False)
    return bytes(result)


def _trim_silence_pcm(data: bytes, channels: int, sample_width: int, sample_rate: int,
                      silence_rms: int = 256, frame_ms: int = 10) -> tuple[bytes, Dict[str, Any]]:
    if not data:
        return data, {'trimmed': False, 'start_frame': 0, 'end_frame': 0}

    frame_size = channels * sample_width
    if frame_size <= 0:
        return data, {'trimmed': False, 'start_frame': 0, 'end_frame': 0}

    chunk_frames = max(1, int(sample_rate * frame_ms / 1000))
    chunk_size = chunk_frames * frame_size
    total_frames = len(data) // frame_size
    chunks = [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]
    active = [
        idx for idx, chunk in enumerate(chunks)
        if chunk and audioop.rms(chunk, sample_width) > silence_rms
    ]
    if not active:
        return b'', {'trimmed': True, 'start_frame': total_frames, 'end_frame': total_frames}

    start_idx = max(0, active[0] - 1)
    end_idx = min(len(chunks), active[-1] + 2)
    trimmed = b''.join(chunks[start_idx:end_idx])
    return trimmed, {
        'trimmed': start_idx > 0 or end_idx < len(chunks),
        'start_frame': start_idx * chunk_frames,
        'end_frame': min(end_idx * chunk_frames, total_frames),
    }


def normalize_wav_source_file(
    src_path: Path,
    dst_path: Path,
    *,
    target_sample_rate: int = _TARGET_SAMPLE_RATE_DEFAULT,
    target_channels: int = _TARGET_CHANNELS_DEFAULT,
    target_sample_width: int = _TARGET_SAMPLE_WIDTH_DEFAULT,
    target_duration_seconds: Optional[float] = None,
    peak_target: float = 0.92,
    fade_ms: int = _FADE_MS_DEFAULT,
    trim_silence: bool = True,
    silence_rms: int = 256,
) -> Dict[str, Any]:
    with wave.open(str(src_path), 'rb') as wav:
        params = wav.getparams()
        if params.comptype not in ('NONE', ''):
            raise ValueError(f'{src_path} is compressed and cannot be normalized with stdlib wave')
        src_channels = wav.getnchannels()
        src_rate = wav.getframerate()
        src_width = wav.getsampwidth()
        raw = wav.readframes(wav.getnframes())

    if src_width not in (1, 2, 3, 4):
        raise ValueError(f'{src_path} uses unsupported sample width: {src_width}')

    peak_before = audioop.max(raw, src_width) if raw else 0
    rms_before = audioop.rms(raw, src_width) if raw else 0

    data = raw
    current_channels = src_channels
    current_rate = src_rate
    current_width = src_width

    if current_channels != target_channels:
        if current_channels == 1 and target_channels == 2:
            data = audioop.tostereo(data, current_width, 1.0, 1.0)
        elif current_channels == 2 and target_channels == 1:
            data = audioop.tomono(data, current_width, 0.5, 0.5)
        else:
            raise ValueError(f'{src_path} channel layout {current_channels} -> {target_channels} is unsupported')
        current_channels = target_channels

    if current_width != target_sample_width:
        data = audioop.lin2lin(data, current_width, target_sample_width)
        current_width = target_sample_width

    if current_rate != target_sample_rate:
        data, _state = audioop.ratecv(data, current_width, current_channels, current_rate, target_sample_rate, None)
        current_rate = target_sample_rate

    trim_meta: Dict[str, Any] = {'trimmed': False, 'start_frame': 0, 'end_frame': 0}
    if trim_silence:
        data, trim_meta = _trim_silence_pcm(
            data,
            current_channels,
            current_width,
            current_rate,
            silence_rms=silence_rms,
        )

    if target_duration_seconds is not None and target_duration_seconds > 0:
        target_frames = int(round(target_duration_seconds * current_rate))
        current_frames = _pcm_frame_count(data, current_channels, current_width)
        frame_size = current_channels * current_width
        if current_frames > target_frames:
            data = data[:target_frames * frame_size]
        elif current_frames < target_frames:
            pad = b'\x00' * ((target_frames - current_frames) * frame_size)
            data = data + pad

    if data:
        peak_after_resample = audioop.max(data, current_width)
        if peak_after_resample > 0 and peak_target > 0:
            target_peak_value = _pcm_peak_ceiling(current_width) * peak_target if peak_target <= 1.0 else peak_target
            scale = target_peak_value / peak_after_resample
            if scale != 1.0:
                data = audioop.mul(data, current_width, scale)
        data = _apply_linear_fade(data, current_channels, current_width, current_rate, fade_in_ms=fade_ms, fade_out_ms=fade_ms)

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dst_path), 'wb') as wav:
        wav.setnchannels(current_channels)
        wav.setsampwidth(current_width)
        wav.setframerate(current_rate)
        wav.writeframes(data)

    frame_count = _pcm_frame_count(data, current_channels, current_width)
    duration = frame_count / current_rate if current_rate else 0.0
    peak_after = audioop.max(data, current_width) if data else 0
    rms_after = audioop.rms(data, current_width) if data else 0
    return {
        'source_file': str(src_path),
        'output_file': str(dst_path),
        'source_channels': src_channels,
        'source_sample_rate': src_rate,
        'source_sample_width': src_width,
        'source_frame_count': len(raw) // max(src_channels * src_width, 1),
        'source_duration_seconds': round((len(raw) // max(src_channels * src_width, 1)) / src_rate if src_rate else 0.0, 6),
        'peak_before': peak_before,
        'rms_before': rms_before,
        'output_channels': current_channels,
        'output_sample_rate': current_rate,
        'output_sample_width': current_width,
        'output_frame_count': frame_count,
        'output_duration_seconds': round(duration, 6),
        'peak_after': peak_after,
        'rms_after': rms_after,
        'target_duration_seconds': target_duration_seconds,
        'trim': trim_meta,
    }


def write_json_manifest(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')


def load_engine_audio_source_shortlist(path: Path = ENGINE_AUDIO_SOURCE_SHORTLIST_PATH) -> Dict[str, List[Dict[str, Any]]]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        return {}
    normalized: Dict[str, List[Dict[str, Any]]] = {}
    for engine_name, rows in payload.items():
        key = str(engine_name).strip()
        if not key or not isinstance(rows, list):
            continue
        normalized[key] = [dict(row) for row in rows if isinstance(row, dict)]
    return normalized


def inventory_sound_profile(root_asset_path: str, asset_index: Dict[str, Path]) -> Dict[str, Any]:
    root_asset_file = resolve_sound_asset_file(root_asset_path, asset_index)
    resolved_root_asset_path = _asset_path_from_uasset_file(root_asset_file)
    sample_slots: List[Dict[str, Any]] = []
    seen_files: set[Path] = set()
    for asset_path in _sound_family_asset_paths(root_asset_path, asset_index):
        try:
            wave_file = resolve_sound_asset_file(asset_path, asset_index)
        except KeyError:
            continue
        if wave_file == root_asset_file or wave_file in seen_files:
            continue
        seen_files.add(wave_file)
        stem = wave_file.stem
        sample_slots.append({
            'asset_path': asset_path,
            'file': str(wave_file),
            'basename': stem,
            'role': 'exhaust' if 'exhaust' in stem.lower() else 'engine',
            'rpm': _rpm_value_from_name(stem),
            'has_ubulk': wave_file.with_suffix('.ubulk').is_file(),
            'has_uexp': wave_file.with_suffix('.uexp').is_file(),
            'duration_hint_seconds': recommended_sample_duration_seconds(stem, _rpm_value_from_name(stem)),
        })
    sample_slots.sort(key=lambda row: (row['rpm'] is None, row['rpm'] or 0, row['basename']))
    return {
        'root_asset_path': root_asset_path,
        'resolved_root_asset_path': resolved_root_asset_path,
        'root_file': str(root_asset_file),
        'family_dir': str(root_asset_file.parent),
        'sample_slots': sample_slots,
    }


def build_engine_sound_inventory(sound_root: Path = VANILLA_SOUND_BASE) -> Dict[str, Any]:
    asset_index = build_sound_asset_index(sound_root)
    entries: List[Dict[str, Any]] = []
    seen_roots: set[Path] = set()

    for asset_path, asset_file in sorted(asset_index.items()):
        stem = asset_file.stem
        family_dir = asset_file.parent
        nested_dir = family_dir / stem
        if not (
            stem.startswith('SC_')
            or stem == 'EngineSoundData'
            or stem.endswith('_EngineSoundData')
            or nested_dir.is_dir()
        ):
            continue
        root_key = asset_file
        if root_key in seen_roots:
            continue
        try:
            profile = inventory_sound_profile(asset_path, asset_index)
        except Exception:
            continue
        seen_roots.add(root_key)
        entries.append(profile)

    entries.sort(key=lambda row: row['root_asset_path'])
    payload = {
        'sound_root': str(sound_root),
        'inventory_count': len(entries),
        'roots': entries,
    }
    return payload


def write_engine_audio_research_manifest(sound_root: Path = VANILLA_SOUND_BASE,
                                         output_path: Path = ENGINE_AUDIO_RESEARCH_PATH / 'vanilla_sound_inventory.json') -> Dict[str, Any]:
    payload = build_engine_sound_inventory(sound_root)
    write_json_manifest(output_path, payload)
    return payload


def clone_sound_root_asset(root_asset_path: str, target_asset_path: str,
                           asset_index: Dict[str, Path], sound_root: Path = MOD_SOUND_BASE) -> Path:
    src_uasset = resolve_sound_asset_file(root_asset_path, asset_index)
    dst_uasset = asset_path_to_output_file(sound_root, target_asset_path)
    clone_uasset_to_new_asset_path(src_uasset, dst_uasset, target_asset_path)
    _copy_optional_sidecar(src_uasset, dst_uasset, '.uexp')
    _copy_optional_sidecar(src_uasset, dst_uasset, '.ubulk')
    return dst_uasset


def clone_sound_family(root_asset_path: str, override_sound_dir: str,
                       asset_index: Dict[str, Path], sound_root: Path = MOD_SOUND_BASE) -> Dict[str, Any]:
    root_asset_file = resolve_sound_asset_file(root_asset_path, asset_index)
    family_paths = _sound_family_asset_paths(root_asset_path, asset_index)
    path_map = {
        asset_path: rewrite_sound_asset_path(asset_path, override_sound_dir)
        for asset_path in family_paths
    }

    copied_assets: List[Dict[str, Any]] = []
    seen_files: set[Path] = set()
    for source_asset_path in family_paths:
        source_file = resolve_sound_asset_file(source_asset_path, asset_index)
        if source_file in seen_files:
            continue
        seen_files.add(source_file)
        target_asset_path = path_map.get(source_asset_path, source_asset_path)
        target_file = asset_path_to_output_file(sound_root, target_asset_path)
        exact_replacements = path_map if source_file == root_asset_file else {source_asset_path: target_asset_path}
        clone_uasset_with_path_map(source_file, target_file, target_asset_path, exact_replacements)
        _copy_optional_sidecar(source_file, target_file, '.uexp')
        _copy_optional_sidecar(source_file, target_file, '.ubulk')
        copied_assets.append({
            'source_asset_path': source_asset_path,
            'target_asset_path': target_asset_path,
            'target_file': str(target_file),
        })

    return {
        'requested_root_asset_path': root_asset_path,
        'resolved_root_asset_path': _asset_path_from_uasset_file(root_asset_file),
        'override_sound_dir': override_sound_dir,
        'copied_assets': copied_assets,
    }


def _encoded_asset_triplet_exists(encoded_dir: Path, basename: str) -> bool:
    stem = encoded_dir / basename
    return stem.with_suffix('.uasset').is_file() and stem.with_suffix('.uexp').is_file() and stem.with_suffix('.ubulk').is_file()


def _encoded_workspace_manifest_path(engine_name: str, workspace_root: Path = ENGINE_AUDIO_WORKSPACE) -> Path:
    return workspace_root / engine_name / 'encoded' / ENGINE_AUDIO_ENCODED_MANIFEST_NAME


def load_encoded_workspace_manifest(engine_name: str, workspace_root: Path = ENGINE_AUDIO_WORKSPACE) -> Dict[str, Any]:
    manifest_path = _encoded_workspace_manifest_path(engine_name, workspace_root=workspace_root)
    if not manifest_path.is_file():
        return {'engine_name': engine_name, 'slots': {}}
    payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    slots = payload.get('slots')
    if not isinstance(slots, dict):
        payload['slots'] = {}
        return payload
    normalized_slots: Dict[str, Dict[str, Any]] = {}
    for slot_name, row in slots.items():
        key = str(slot_name).strip()
        if not key:
            continue
        if isinstance(row, dict):
            normalized_row = dict(row)
        else:
            normalized_row = {}
        if 'enabled' not in normalized_row:
            normalized_row['enabled'] = True
        normalized_slots[key] = normalized_row
    payload['slots'] = normalized_slots
    return payload


def save_encoded_workspace_manifest(engine_name: str, slots: Dict[str, Dict[str, Any]],
                                    workspace_root: Path = ENGINE_AUDIO_WORKSPACE) -> Dict[str, Any]:
    payload = {
        'engine_name': engine_name,
        'slots': slots,
    }
    write_json_manifest(_encoded_workspace_manifest_path(engine_name, workspace_root=workspace_root), payload)
    return payload


def update_encoded_workspace_manifest(engine_name: str, slot_basename: str,
                                      source_asset_path: Optional[str],
                                      workspace_root: Path = ENGINE_AUDIO_WORKSPACE) -> Dict[str, Any]:
    payload = load_encoded_workspace_manifest(engine_name, workspace_root=workspace_root)
    slots = dict(payload.get('slots') or {})
    row = dict(slots.get(slot_basename) or {})
    if source_asset_path:
        row['source_asset_path'] = str(source_asset_path)
    row.setdefault('enabled', True)
    slots[slot_basename] = row
    return save_encoded_workspace_manifest(engine_name, slots, workspace_root=workspace_root)


def set_encoded_workspace_slot_enabled(engine_name: str, slot_basename: str, enabled: bool,
                                       workspace_root: Path = ENGINE_AUDIO_WORKSPACE) -> Dict[str, Any]:
    payload = load_encoded_workspace_manifest(engine_name, workspace_root=workspace_root)
    slots = dict(payload.get('slots') or {})
    row = dict(slots.get(slot_basename) or {})
    row['enabled'] = bool(enabled)
    slots[slot_basename] = row
    return save_encoded_workspace_manifest(engine_name, slots, workspace_root=workspace_root)


def _import_encoded_sound_asset(encoded_uasset: Path, target_asset_path: str, sound_root: Path,
                                declared_source_asset_path: Optional[str] = None) -> Dict[str, Any]:
    target_file = asset_path_to_output_file(sound_root, target_asset_path)
    source_asset_path = str(declared_source_asset_path or '').strip() or _asset_path_from_uasset_file(encoded_uasset)
    if source_asset_path == target_asset_path:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(encoded_uasset, target_file)
        shutil.copy2(_require_sidecar(encoded_uasset, '.uexp'), target_file.with_suffix('.uexp'))
        shutil.copy2(_require_sidecar(encoded_uasset, '.ubulk'), target_file.with_suffix('.ubulk'))
        return {
            'source_asset_path': source_asset_path,
            'target_asset_path': target_asset_path,
            'target_file': str(target_file),
            'source_mode': 'encoded-direct-copy',
        }
    if not source_asset_path:
        raise ValueError(f'Cannot determine asset path for encoded asset: {encoded_uasset}')
    clone_uasset_with_path_map(
        encoded_uasset,
        target_file,
        target_asset_path,
        {source_asset_path: target_asset_path},
    )
    shutil.copy2(_require_sidecar(encoded_uasset, '.uexp'), target_file.with_suffix('.uexp'))
    shutil.copy2(_require_sidecar(encoded_uasset, '.ubulk'), target_file.with_suffix('.ubulk'))
    return {
        'source_asset_path': source_asset_path,
        'target_asset_path': target_asset_path,
        'target_file': str(target_file),
        'source_mode': 'encoded-import',
    }


def _load_wav_metadata(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    with wave.open(str(path), 'rb') as wav:
        frames = int(wav.getnframes())
        sample_rate = int(wav.getframerate())
        channels = int(wav.getnchannels())
        duration = (frames / sample_rate) if sample_rate else 0.0
        return {
            'frames': frames,
            'sample_rate': sample_rate,
            'channels': channels,
            'duration_seconds': duration,
        }


def _legacy_soundwave_transplant_uexp(shell_uexp: Path, encoded_uexp: Path,
                                      wav_metadata: Optional[Dict[str, Any]] = None) -> bytes:
    shell_bytes = bytearray(shell_uexp.read_bytes())
    encoded_bytes = encoded_uexp.read_bytes()

    shell_tail_offset = shell_bytes.find(b'ABEU')
    encoded_tail_offset = encoded_bytes.find(b'ABEU')
    if shell_tail_offset < 0 or encoded_tail_offset < 0:
        raise ValueError('Cannot locate ABEU trailer for SoundWave transplant')

    shell_tail_len = len(shell_bytes) - shell_tail_offset
    encoded_tail_len = len(encoded_bytes) - encoded_tail_offset
    if shell_tail_len != encoded_tail_len:
        raise ValueError(
            f'SoundWave transplant trailer mismatch: shell={shell_tail_len}, encoded={encoded_tail_len}'
        )

    if wav_metadata:
        shell_bytes[6:8] = struct.pack('<H', int(wav_metadata['channels']))
        shell_bytes[10:14] = struct.pack('<I', int(wav_metadata['sample_rate']))
        shell_bytes[14:18] = struct.pack('<f', float(wav_metadata['duration_seconds']))
        shell_bytes[18:22] = struct.pack('<f', float(wav_metadata['frames']))

    shell_bytes[shell_tail_offset:] = encoded_bytes[encoded_tail_offset:]
    return bytes(shell_bytes)


def _import_encoded_sound_asset_with_shell(encoded_uasset: Path,
                                           shell_uasset: Path,
                                           shell_asset_path: str,
                                           target_asset_path: str,
                                           sound_root: Path) -> Dict[str, Any]:
    target_file = asset_path_to_output_file(sound_root, target_asset_path)
    clone_uasset_with_path_map(shell_uasset, target_file, target_asset_path, {shell_asset_path: target_asset_path})

    normalized_wav = encoded_uasset.parent.parent / 'normalized' / f'{encoded_uasset.stem}_normalized.wav'
    wav_metadata = _load_wav_metadata(normalized_wav)
    transplanted_uexp = _legacy_soundwave_transplant_uexp(
        shell_uasset.with_suffix('.uexp'),
        _require_sidecar(encoded_uasset, '.uexp'),
        wav_metadata=wav_metadata,
    )
    target_file.with_suffix('.uexp').write_bytes(transplanted_uexp)
    shutil.copy2(_require_sidecar(encoded_uasset, '.ubulk'), target_file.with_suffix('.ubulk'))

    return {
        'source_asset_path': shell_asset_path,
        'target_asset_path': target_asset_path,
        'target_file': str(target_file),
        'source_mode': 'encoded-transplanted-shell',
        'normalized_wav': str(normalized_wav) if normalized_wav.is_file() else '',
    }


def sync_engine_sound_bank(engine_name: str, root_asset_path: str, override_sound_dir: str,
                           asset_index: Dict[str, Path],
                           sound_root: Path = MOD_SOUND_BASE,
                           workspace_root: Path = ENGINE_AUDIO_WORKSPACE) -> Dict[str, Any]:
    root_asset_file = resolve_sound_asset_file(root_asset_path, asset_index)
    family_paths = _sound_family_asset_paths(root_asset_path, asset_index)
    resolved_root_asset_path = _asset_path_from_uasset_file(root_asset_file)
    encoded_dir = workspace_root / engine_name / 'encoded'
    encoded_manifest = load_encoded_workspace_manifest(engine_name, workspace_root=workspace_root)
    encoded_slots = dict(encoded_manifest.get('slots') or {})

    encoded_source_paths: Dict[str, str] = {}
    for source_asset_path in family_paths:
        source_file = resolve_sound_asset_file(source_asset_path, asset_index)
        slot_row = dict(encoded_slots.get(source_file.stem) or {})
        slot_enabled = bool(slot_row.get('enabled', True))
        if slot_enabled and _encoded_asset_triplet_exists(encoded_dir, source_file.stem):
            encoded_source_paths[source_asset_path] = rewrite_sound_asset_path(source_asset_path, override_sound_dir)

    path_map: Dict[str, str] = {
        resolved_root_asset_path: rewrite_sound_asset_path(resolved_root_asset_path, override_sound_dir),
        root_asset_path: rewrite_sound_asset_path(root_asset_path, override_sound_dir),
    }
    path_map.update(encoded_source_paths)

    copied_assets: List[Dict[str, Any]] = []
    imported_count = 0
    vanilla_count = 0
    referenced_vanilla_assets = 0
    seen_files: set[Path] = set()
    for source_asset_path in family_paths:
        source_file = resolve_sound_asset_file(source_asset_path, asset_index)
        if source_file in seen_files:
            continue
        seen_files.add(source_file)
        target_asset_path = path_map.get(source_asset_path, source_asset_path)
        target_file = asset_path_to_output_file(sound_root, target_asset_path)

        if source_file == root_asset_file:
            clone_uasset_with_path_map(source_file, target_file, target_asset_path, path_map)
            _copy_optional_sidecar(source_file, target_file, '.uexp')
            _copy_optional_sidecar(source_file, target_file, '.ubulk')
            copied_assets.append({
                'source_asset_path': source_asset_path,
                'target_asset_path': target_asset_path,
                'target_file': str(target_file),
                'source_mode': 'vanilla-root-clone',
            })
            vanilla_count += 1
            continue

        encoded_uasset = encoded_dir / f'{source_file.stem}.uasset'
        slot_row = dict(encoded_slots.get(source_file.stem) or {})
        slot_enabled = bool(slot_row.get('enabled', True))
        if slot_enabled and _encoded_asset_triplet_exists(encoded_dir, source_file.stem):
            declared_source_asset_path = str(slot_row.get('source_asset_path') or '').strip()
            encoded_self_path = ''
            try:
                encoded_self_path = _asset_path_from_uasset_file(encoded_uasset)
            except Exception:
                encoded_self_path = ''
            if encoded_self_path.startswith(_SOUND_PREFIX):
                copied_assets.append(_import_encoded_sound_asset(
                    encoded_uasset,
                    target_asset_path,
                    sound_root,
                    declared_source_asset_path=declared_source_asset_path or None,
                ))
            else:
                copied_assets.append(_import_encoded_sound_asset_with_shell(
                    encoded_uasset,
                    source_file,
                    source_asset_path,
                    target_asset_path,
                    sound_root,
                ))
            imported_count += 1
            continue

        copied_assets.append({
            'source_asset_path': source_asset_path,
            'target_asset_path': source_asset_path,
            'target_file': '',
            'source_mode': 'vanilla-reference',
        })
        referenced_vanilla_assets += 1

    return {
        'engine_name': engine_name,
        'requested_root_asset_path': root_asset_path,
        'resolved_root_asset_path': resolved_root_asset_path,
        'override_sound_dir': override_sound_dir,
        'imported_encoded_assets': imported_count,
        'copied_vanilla_assets': vanilla_count,
        'referenced_vanilla_assets': referenced_vanilla_assets,
        'copied_assets': copied_assets,
        'encoded_dir': str(encoded_dir),
    }


def update_primary_engine_sound_asset(uasset_path: Path, new_sound_asset_path: str) -> bool:
    current_asset_path = primary_engine_sound_path(uasset_path)
    if not current_asset_path or current_asset_path == new_sound_asset_path:
        return False
    self_asset_path = _asset_path_from_uasset_file(uasset_path)
    clone_uasset_with_path_map(
        uasset_path,
        uasset_path,
        self_asset_path,
        {current_asset_path: new_sound_asset_path},
    )
    return True


def detect_local_audio_toolchain() -> Dict[str, Any]:
    search_names = {
        'unreal_editor': 'UnrealEditor.exe',
        'unreal_editor_cmd': 'UnrealEditor-Cmd.exe',
        'unreal_pak': 'UnrealPak.exe',
        'ffmpeg': 'ffmpeg.exe',
        'ffprobe': 'ffprobe.exe',
        'quickbms': 'quickbms.exe',
        'bink_encoder': 'bink2enc.exe',
    }
    common_roots = [
        Path(r'C:\Program Files (x86)\Steam\steamapps\common\Motor Town\MotorTown\Binaries\Win64'),
        Path(r'C:\Program Files (x86)\Steam\steamapps\common\Motor Town\MotorTown\Content'),
    ]
    common_roots.extend(_discover_epic_unreal_roots())
    resolved: Dict[str, str] = {}
    for key, exe_name in search_names.items():
        found = shutil.which(exe_name)
        if found:
            resolved[key] = found
            continue
        for root in common_roots:
            candidate = root / exe_name
            if candidate.is_file():
                resolved[key] = str(candidate)
                break

    capabilities = {
        'can_encode_binka_direct': bool(resolved.get('bink_encoder')),
        'can_cook_with_unreal': bool(resolved.get('unreal_editor') or resolved.get('unreal_editor_cmd')),
        'can_transcode_wav': bool(resolved.get('ffmpeg')),
        'can_import_preencoded_assets': True,
    }
    payload = {
        'tools': {key: resolved.get(key, '') for key in search_names},
        'search_roots': [str(path) for path in common_roots],
        'capabilities': capabilities,
        'recommended_path': (
            'direct-bink-encode'
            if capabilities['can_encode_binka_direct']
            else 'unreal-cook-import'
            if capabilities['can_cook_with_unreal']
            else 'preencoded-soundwave-import'
        ),
    }
    return payload


def write_local_audio_toolchain_report(output_path: Path = ENGINE_AUDIO_TOOLCHAIN_PATH) -> Dict[str, Any]:
    payload = detect_local_audio_toolchain()
    write_json_manifest(output_path, payload)
    return payload


def _engine_association_from_toolchain(toolchain: Optional[Dict[str, Any]] = None) -> str:
    toolchain = toolchain or detect_local_audio_toolchain()
    editor_path = str((toolchain.get('tools') or {}).get('unreal_editor') or (toolchain.get('tools') or {}).get('unreal_editor_cmd') or '')
    if editor_path:
        parts = Path(editor_path).parts
        for part in reversed(parts):
            if part.startswith('UE_'):
                return part.removeprefix('UE_')
    return '5.6'


def ensure_unreal_audio_project(project_root: Path = UNREAL_AUDIO_PROJECT_ROOT,
                                toolchain: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    toolchain = toolchain or detect_local_audio_toolchain()
    uproject_path = project_root / f'{UNREAL_AUDIO_PROJECT_NAME}.uproject'
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / 'Content').mkdir(parents=True, exist_ok=True)
    (project_root / 'Config').mkdir(parents=True, exist_ok=True)
    (project_root / 'Saved').mkdir(parents=True, exist_ok=True)
    (project_root / UNREAL_AUDIO_DDC_DIRNAME).mkdir(parents=True, exist_ok=True)

    uproject_payload = {
        'FileVersion': 3,
        'EngineAssociation': _engine_association_from_toolchain(toolchain),
        'Category': '',
        'Description': 'Temporary Unreal project for Frog Mod Editor engine-audio import/cook tasks.',
        'Plugins': [
            {'Name': 'PythonScriptPlugin', 'Enabled': True},
            {'Name': 'EditorScriptingUtilities', 'Enabled': True},
        ],
    }
    uproject_path.parent.mkdir(parents=True, exist_ok=True)
    uproject_path.write_text(json.dumps(uproject_payload, indent=2), encoding='utf-8')

    default_engine_ini = '\n'.join([
        '[/Script/EngineSettings.GeneralProjectSettings]',
        f'ProjectName={UNREAL_AUDIO_PROJECT_NAME}',
        '',
        '[/Script/UnrealEd.ProjectPackagingSettings]',
        'UsePakFile=False',
        'bUseIoStore=False',
        'bCompressed=False',
        '',
        '[Audio]',
        '+AllWaveFormats=BINKA',
        '+FormatModuleHints=AudioFormatBINK',
        '+AudioInfoModules=BinkAudioDecoder',
        'FallbackFormat=BINKA',
        'PlatformFormat=BINKA',
        'PlatformStreamingFormat=BINKA',
        '',
    ])
    (project_root / 'Config' / 'DefaultEngine.ini').write_text(default_engine_ini, encoding='utf-8')

    return {
        'project_root': str(project_root),
        'uproject_path': str(uproject_path),
        'engine_association': uproject_payload['EngineAssociation'],
        'ddc_root': str(project_root / UNREAL_AUDIO_DDC_DIRNAME),
    }


def _unreal_audio_ddc_root(project_root: Path) -> Path:
    return project_root / UNREAL_AUDIO_DDC_DIRNAME


def _unreal_audio_cook_dir(project_root: Path, engine_name: str) -> Path:
    return project_root / 'Content' / 'EngineAudioImports' / engine_name


def _build_unreal_audio_env(project_root: Path,
                            base_env: Optional[Dict[str, str]] = None,
                            extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = dict(base_env or os.environ.copy())
    ddc_root = _unreal_audio_ddc_root(project_root)
    ddc_root.mkdir(parents=True, exist_ok=True)
    env['UE-LocalDataCachePath'] = str(ddc_root)
    if extra_env:
        env.update(extra_env)
    return env


def _classify_unreal_import_issues(stdout: str, stderr: str) -> Dict[str, Any]:
    combined = '\n'.join(part for part in (stdout, stderr) if part)
    known_issues: List[Dict[str, str]] = []

    def _add_issue(code: str, message: str) -> None:
        if any(row['code'] == code for row in known_issues):
            return
        known_issues.append({'code': code, 'message': message})

    if "Decoder for AudioFormat 'BINKA' not found" in combined:
        _add_issue(
            'binka_decoder_missing_after_import',
            'Unreal imported the SoundWave but raised a handled ensure while resolving the BINKA decoder.',
        )
    if 'Imported audio has DC offsets larger than 100' in combined:
        _add_issue(
            'wav_tail_dc_offset_warning',
            'The normalized WAV still ended away from zero, so Unreal warned that the loop tail may pop.',
        )
    if 'Unable to open ROOT certificate store' in combined:
        _add_issue(
            'windows_root_store_unavailable',
            'Unreal emitted a platform SSL certificate warning during startup.',
        )

    known_codes = {row['code'] for row in known_issues}
    nonfatal_codes = {
        'binka_decoder_missing_after_import',
        'windows_root_store_unavailable',
    }
    cosmetic_codes = {
        'windows_root_store_unavailable',
    }
    return {
        'known_issues': known_issues,
        'known_nonfatal_returncode': bool(known_codes) and known_codes.issubset(nonfatal_codes),
        'cosmetic_only': bool(known_codes) and known_codes.issubset(cosmetic_codes),
        'clean': not known_issues or known_codes.issubset(cosmetic_codes),
    }


def _source_wav_for_slot(profile: Dict[str, Any], slot_basename: str) -> Optional[Path]:
    paths = profile.get('paths') or {}
    normalized_dir = Path(str(paths.get('normalized') or ''))
    raw_dir = Path(str(paths.get('raw') or ''))
    candidates = [
        normalized_dir / f'{slot_basename}_normalized.wav',
        raw_dir / f'{slot_basename}.wav',
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _asset_directory(asset_path: str) -> str:
    if '/' not in asset_path:
        return asset_path
    return asset_path.rsplit('/', 1)[0]


def _project_content_path_from_asset_dir(project_root: Path, asset_dir: str) -> Path:
    if not asset_dir.startswith('/Game/'):
        raise ValueError(f'Expected a /Game asset directory, got: {asset_dir}')
    relative_parts = [part for part in asset_dir[len('/Game/'):].split('/') if part]
    return project_root.joinpath('Content', *relative_parts)


def build_unreal_audio_import_job(engine_name: str,
                                  workspace_root: Path = ENGINE_AUDIO_WORKSPACE) -> Dict[str, Any]:
    profile = load_engine_audio_workspace_profile(engine_name, workspace_root=workspace_root)
    imports: List[Dict[str, Any]] = []
    missing_slots: List[str] = []
    destination_paths: List[str] = []

    for slot in profile.get('sample_slots', []):
        slot_basename = str(slot.get('basename') or '').strip()
        if not slot_basename:
            continue
        source_wav = _source_wav_for_slot(profile, slot_basename)
        if source_wav is None:
            missing_slots.append(slot_basename)
            continue
        source_asset_path = str(slot.get('asset_path') or '').strip()
        if not source_asset_path:
            missing_slots.append(slot_basename)
            continue
        target_asset_path = rewrite_sound_asset_path(source_asset_path, str(profile.get('override_sound_dir') or engine_name))
        destination_path = _asset_directory(target_asset_path)
        imports.append({
            'slot_basename': slot_basename,
            'source_asset_path': source_asset_path,
            'target_asset_path': target_asset_path,
            'source_file': str(source_wav),
            'destination_path': destination_path,
            'destination_name': slot_basename,
            'role': slot.get('role'),
            'rpm': slot.get('rpm'),
        })
        destination_paths.append(destination_path)

    if not imports:
        raise FileNotFoundError(
            f'No matching WAV inputs found for {engine_name}. '
            f'Add exact slot files under raw/ or normalized/ first.'
        )

    return {
        'engine_name': engine_name,
        'project_name': UNREAL_AUDIO_PROJECT_NAME,
        'destination_path': _ordered_unique(destination_paths)[0],
        'destination_paths': _ordered_unique(destination_paths),
        'imports': imports,
        'missing_slots': missing_slots,
        'workspace_root': str(workspace_root),
    }


def import_engine_audio_with_unreal(engine_name: str,
                                    workspace_root: Path = ENGINE_AUDIO_WORKSPACE,
                                    project_root: Path = UNREAL_AUDIO_PROJECT_ROOT,
                                    editor_cmd_path: Optional[Path | str] = None,
                                    *,
                                    request_cook: bool = False,
                                    target_platform: str = 'Windows') -> Dict[str, Any]:
    toolchain = detect_local_audio_toolchain()
    if not toolchain.get('capabilities', {}).get('can_cook_with_unreal'):
        raise RuntimeError('Unreal Editor commandlet support is not available on this machine.')

    editor_cmd = Path(str(editor_cmd_path or toolchain.get('tools', {}).get('unreal_editor_cmd') or ''))
    if not editor_cmd.is_file():
        raise FileNotFoundError(f'UnrealEditor-Cmd.exe not found: {editor_cmd}')

    project_info = ensure_unreal_audio_project(project_root=project_root, toolchain=toolchain)
    job = build_unreal_audio_import_job(engine_name, workspace_root=workspace_root)

    UNREAL_AUDIO_JOB_ROOT.mkdir(parents=True, exist_ok=True)
    job_path = UNREAL_AUDIO_JOB_ROOT / f'{engine_name}_import_job.json'
    report_path = UNREAL_AUDIO_JOB_ROOT / f'{engine_name}_import_report.json'
    write_json_manifest(job_path, job)
    if report_path.exists():
        report_path.unlink()

    env = _build_unreal_audio_env(project_root, extra_env={
            'FROG_MOD_EDITOR_UNREAL_AUDIO_JOB': str(job_path),
            'FROG_MOD_EDITOR_UNREAL_AUDIO_REPORT': str(report_path),
            'FROG_MOD_EDITOR_UNREAL_AUDIO_COOK': '1' if request_cook else '0',
            'FROG_MOD_EDITOR_UNREAL_AUDIO_COOK_PLATFORM': target_platform,
            'FROG_MOD_EDITOR_UNREAL_AUDIO_COOK_SUBDIR': f'FrogModEditorCooked/{engine_name}',
    })

    import_result = _run_external_command([
        str(editor_cmd),
        project_info['uproject_path'],
        '-run=pythonscript',
        f'-script={UNREAL_AUDIO_SCRIPT_PATH}',
        '-unattended',
        '-NoCrashDialog',
        '-nop4',
        '-nosplash',
        '-nullrhi',
        '-DDC=InstalledNoZenLocalFallback',
        '-stdout',
        '-FullStdOutLogOutput',
        '-UTF8Output',
    ], env=env, cwd=project_root)

    unreal_report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.is_file() else {}
    import_ok = bool(unreal_report.get('ok'))
    import_issues = _classify_unreal_import_issues(import_result['stdout'], import_result['stderr'])
    tolerated_nonfatal = (
        import_result['returncode'] != 0
        and import_ok
        and bool(import_issues.get('known_nonfatal_returncode'))
    )
    if import_result['returncode'] != 0 and not import_ok:
        raise RuntimeError(
            f'Unreal import failed for {engine_name}: '
            f'{import_result["stderr"] or import_result["stdout"]}'
        )

    return {
        'engine_name': engine_name,
        'project': project_info,
        'job_path': str(job_path),
        'report_path': str(report_path),
        'import_job': job,
        'unreal_import_report': unreal_report,
        'import_command': import_result['command'],
        'import_returncode': import_result['returncode'],
        'import_stdout_tail': import_result['stdout'][-4000:],
        'import_stderr_tail': import_result['stderr'][-4000:],
        'import_status': (
            'clean'
            if import_result['returncode'] == 0 and import_issues.get('clean')
            else 'warning'
            if import_ok or tolerated_nonfatal
            else 'failed'
        ),
        'known_import_issues': import_issues.get('known_issues', []),
        'known_nonfatal_returncode': tolerated_nonfatal,
        'toolchain': toolchain,
        'requested_cook': bool(request_cook),
    }


def _run_external_command(args: List[str], *, env: Optional[Dict[str, str]] = None,
                          cwd: Optional[Path] = None, timeout_seconds: int = 1800) -> Dict[str, Any]:
    completed = subprocess.run(
        args,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=timeout_seconds,
    )
    return {
        'command': args,
        'returncode': int(completed.returncode),
        'stdout': completed.stdout,
        'stderr': completed.stderr,
    }


def _copy_cooked_triplet(cooked_base: Path, encoded_dir: Path, slot_basename: str) -> Dict[str, Any]:
    copied_files: List[str] = []
    missing_files: List[str] = []
    for suffix in ('.uasset', '.uexp', '.ubulk'):
        src = cooked_base.with_suffix(suffix)
        dst = encoded_dir / f'{slot_basename}{suffix}'
        if not src.is_file():
            missing_files.append(str(src))
            continue
        encoded_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied_files.append(str(dst))
    return {
        'slot_basename': slot_basename,
        'source_base': str(cooked_base),
        'copied_files': copied_files,
        'missing_files': missing_files,
        'complete': not missing_files,
    }


def _copy_cooked_triplet_from_report(cooked_row: Dict[str, Any], encoded_dir: Path, slot_basename: str) -> Dict[str, Any]:
    copied_files: List[str] = []
    missing_files: List[str] = []
    file_map = {
        '.uasset': str(cooked_row.get('uasset') or ''),
        '.uexp': str(cooked_row.get('uexp') or ''),
        '.ubulk': str(cooked_row.get('ubulk') or ''),
    }
    for suffix, src_text in file_map.items():
        if not src_text:
            missing_files.append(src_text or f'<missing:{suffix}>')
            continue
        src = Path(src_text)
        dst = encoded_dir / f'{slot_basename}{suffix}'
        if not src.is_file():
            missing_files.append(str(src))
            continue
        encoded_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied_files.append(str(dst))
    return {
        'slot_basename': slot_basename,
        'source_base': str(cooked_row.get('uasset') or ''),
        'copied_files': copied_files,
        'missing_files': missing_files,
        'complete': len(missing_files) == 0,
    }


def _find_cooked_asset_base(project_root: Path, engine_name: str, slot_basename: str,
                            target_asset_path: Optional[str] = None) -> Optional[Path]:
    cooked_root = project_root / 'Saved' / 'Cooked'
    if not cooked_root.is_dir():
        return None
    normalized_parts: List[str] = []
    if target_asset_path and target_asset_path.startswith('/Game/'):
        normalized_parts = [
            part.lower()
            for part in target_asset_path[len('/Game/'):].split('/')[:-1]
            if part
        ]
    if not normalized_parts:
        normalized_parts = [engine_name.lower()]
    for candidate in cooked_root.rglob(f'{slot_basename}.uasset'):
        parent_parts = [part.lower() for part in candidate.parts]
        if all(token in parent_parts for token in normalized_parts):
            return candidate.with_suffix('')
    return None


def cook_engine_audio_with_unreal(engine_name: str,
                                  workspace_root: Path = ENGINE_AUDIO_WORKSPACE,
                                  project_root: Path = UNREAL_AUDIO_PROJECT_ROOT,
                                  editor_cmd_path: Optional[Path | str] = None,
                                  target_platform: str = 'Windows') -> Dict[str, Any]:
    toolchain = detect_local_audio_toolchain()
    editor_cmd = Path(str(editor_cmd_path or toolchain.get('tools', {}).get('unreal_editor_cmd') or ''))
    if not editor_cmd.is_file():
        raise FileNotFoundError(f'UnrealEditor-Cmd.exe not found: {editor_cmd}')

    import_phase = import_engine_audio_with_unreal(
        engine_name,
        workspace_root=workspace_root,
        project_root=project_root,
        editor_cmd_path=editor_cmd_path,
        request_cook=False,
        target_platform=target_platform,
    )
    job = dict(import_phase['import_job'])
    encoded_dir = Path(load_engine_audio_workspace_profile(engine_name, workspace_root=workspace_root)['paths']['encoded'])
    project_info = dict(import_phase['project'])
    report_path = Path(import_phase['report_path'])
    unreal_report = dict(import_phase['unreal_import_report'])
    import_result = {
        'command': import_phase['import_command'],
        'returncode': int(import_phase['import_returncode']),
        'stdout': import_phase['import_stdout_tail'],
        'stderr': import_phase['import_stderr_tail'],
    }

    copied_triplets: List[Dict[str, Any]] = []
    missing_cooked_slots: List[str] = []
    cooked_rows_by_name = {
        str(row.get('basename') or '').strip(): row
        for row in unreal_report.get('cooked_assets', [])
        if str(row.get('basename') or '').strip()
    }

    if cooked_rows_by_name:
        for item in job['imports']:
            slot_basename = str(item['slot_basename'])
            cooked_row = cooked_rows_by_name.get(slot_basename)
            if not cooked_row:
                missing_cooked_slots.append(slot_basename)
                continue
            copied_triplets.append(_copy_cooked_triplet_from_report(cooked_row, encoded_dir, slot_basename))
        cook_result = {
            'command': import_result['command'],
            'returncode': import_result['returncode'],
            'stdout': import_result['stdout'],
            'stderr': import_result['stderr'],
        }
    else:
        cook_dirs = [
            _project_content_path_from_asset_dir(project_root, str(asset_dir))
            for asset_dir in (job.get('destination_paths') or [job.get('destination_path')])
            if str(asset_dir or '').strip()
        ]
        if not cook_dirs:
            cook_dirs = [_unreal_audio_cook_dir(project_root, engine_name)]
        cook_env = _build_unreal_audio_env(project_root)
        cook_args = [
            str(editor_cmd),
            project_info['uproject_path'],
            '-run=Cook',
            f'-TargetPlatform={target_platform}',
            '-DDC=InstalledNoZenLocalFallback',
            '-unattended',
            '-NoCrashDialog',
            '-nop4',
            '-stdout',
            '-FullStdOutLogOutput',
            '-UTF8Output',
        ]
        cook_args.extend(f'-CookDir={cook_dir.as_posix()}' for cook_dir in cook_dirs)
        cook_result = _run_external_command(cook_args, env=cook_env, cwd=project_root)
        for item in job['imports']:
            slot_basename = str(item['slot_basename'])
            cooked_base = _find_cooked_asset_base(
                project_root,
                engine_name,
                slot_basename,
                target_asset_path=str(item.get('target_asset_path') or ''),
            )
            if cooked_base is None:
                missing_cooked_slots.append(slot_basename)
                continue
            copied_triplets.append(_copy_cooked_triplet(cooked_base, encoded_dir, slot_basename))
        if cook_result['returncode'] != 0 and not any(row.get('complete') for row in copied_triplets):
            raise RuntimeError(
                f'Unreal cook failed for {engine_name}: '
                f'{cook_result["stderr"] or cook_result["stdout"]}'
            )

    manifest_slots = dict((load_encoded_workspace_manifest(engine_name, workspace_root=workspace_root)).get('slots') or {})
    target_paths_by_slot = {
        str(item.get('slot_basename') or '').strip(): str(item.get('target_asset_path') or '').strip()
        for item in job.get('imports', [])
        if str(item.get('slot_basename') or '').strip()
    }
    for copied in copied_triplets:
        if not copied.get('complete'):
            continue
        slot_basename = str(copied.get('slot_basename') or '').strip()
        if not slot_basename:
            continue
        target_asset_path = target_paths_by_slot.get(slot_basename)
        if not target_asset_path:
            continue
        row = dict(manifest_slots.get(slot_basename) or {})
        row['source_asset_path'] = target_asset_path
        manifest_slots[slot_basename] = row
    save_encoded_workspace_manifest(engine_name, manifest_slots, workspace_root=workspace_root)

    return {
        'engine_name': engine_name,
        'project': project_info,
        'job_path': str(import_phase['job_path']),
        'report_path': str(import_phase['report_path']),
        'import_job': job,
        'unreal_import_report': unreal_report,
        'import_command': import_result['command'],
        'cook_command': cook_result['command'],
        'import_stdout_tail': import_result['stdout'][-4000:],
        'import_stderr_tail': import_result['stderr'][-4000:],
        'cook_stdout_tail': cook_result['stdout'][-4000:],
        'cook_stderr_tail': cook_result['stderr'][-4000:],
        'copied_triplets': copied_triplets,
        'complete_triplets': sum(1 for row in copied_triplets if row.get('complete')),
        'missing_cooked_slots': missing_cooked_slots,
        'missing_source_slots': list(job.get('missing_slots') or []),
        'encoded_dir': str(encoded_dir),
        'ddc_root': str(_unreal_audio_ddc_root(project_root)),
        'toolchain': toolchain,
    }


def load_engine_audio_overrides(path: Path = ENGINE_AUDIO_OVERRIDE_PATH) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def save_engine_audio_overrides(overrides: Dict[str, Any], path: Path = ENGINE_AUDIO_OVERRIDE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides, indent=2, sort_keys=True), encoding='utf-8')


def set_engine_audio_override(engine_name: str, enabled: bool,
                              override_sound_dir: Optional[str] = None,
                              path: Path = ENGINE_AUDIO_OVERRIDE_PATH) -> Dict[str, Any]:
    overrides = load_engine_audio_overrides(path)
    row = dict(overrides.get(engine_name) or {})
    row['enabled'] = bool(enabled)
    if override_sound_dir:
        row['override_sound_dir'] = str(override_sound_dir).strip()
    overrides[engine_name] = row
    save_engine_audio_overrides(overrides, path)
    return row


def resolve_sound_dir_override(engine_name: str, default_sound_dir: Optional[str] = None,
                               overrides: Optional[Dict[str, Any]] = None) -> Optional[str]:
    overrides = overrides if overrides is not None else load_engine_audio_overrides()
    row = overrides.get(engine_name) or {}
    if row.get('enabled'):
        return row.get('override_sound_dir') or default_sound_dir
    return default_sound_dir


def disable_all_engine_audio_overrides(path: Path = ENGINE_AUDIO_OVERRIDE_PATH) -> Dict[str, Any]:
    overrides = load_engine_audio_overrides(path)
    for row in overrides.values():
        if isinstance(row, dict):
            row['enabled'] = False
    save_engine_audio_overrides(overrides, path)
    return overrides


def sync_enabled_sound_overrides(manifest_path: Path = ENGINE_AUDIO_MANIFEST_PATH,
                                 overrides_path: Path = ENGINE_AUDIO_OVERRIDE_PATH,
                                 mod_sound_root: Path = MOD_SOUND_BASE,
                                 workspace_root: Path = ENGINE_AUDIO_WORKSPACE) -> Dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else {}
    overrides = load_engine_audio_overrides(overrides_path)
    asset_index = build_sound_asset_index()

    if mod_sound_root.exists():
        shutil.rmtree(mod_sound_root)
    mod_sound_root.mkdir(parents=True, exist_ok=True)

    synced: List[str] = []
    skipped: List[str] = []
    copied_assets = 0
    imported_encoded_assets = 0
    referenced_vanilla_assets = 0

    for row in manifest.get('engines', []):
        engine_name = str(row.get('engine_name') or '').strip()
        override = overrides.get(engine_name) or {}
        if not override.get('enabled'):
            skipped.append(engine_name)
            continue
        root_asset_path = str(override.get('vanilla_sound_asset') or row.get('vanilla_sound_asset') or '').strip()
        override_sound_dir = str(override.get('override_sound_dir') or row.get('override_sound_dir') or '').strip()
        if not root_asset_path or not override_sound_dir:
            skipped.append(engine_name)
            continue
        report = sync_engine_sound_bank(
            engine_name,
            root_asset_path,
            override_sound_dir,
            asset_index,
            sound_root=mod_sound_root,
            workspace_root=workspace_root,
        )
        copied_assets += sum(1 for item in report['copied_assets'] if str(item.get('target_file') or '').strip())
        imported_encoded_assets += int(report.get('imported_encoded_assets') or 0)
        referenced_vanilla_assets += int(report.get('referenced_vanilla_assets') or 0)
        synced.append(engine_name)

    return {
        'synced_engines': len(synced),
        'copied_assets': copied_assets,
        'imported_encoded_assets': imported_encoded_assets,
        'referenced_vanilla_assets': referenced_vanilla_assets,
        'engines': synced,
        'skipped_engines': skipped,
        'mod_sound_root': str(mod_sound_root),
    }


def _match_sample_slot(source_name: str, sample_slots: List[Dict[str, Any]]) -> Dict[str, Any]:
    source_rpm = _rpm_value_from_name(source_name)
    source_is_exhaust = 'exhaust' in source_name.lower()

    if source_rpm is not None:
        exact = [
            slot for slot in sample_slots
            if slot.get('rpm') == source_rpm and (slot.get('role') == 'exhaust') == source_is_exhaust
        ]
        if exact:
            return {'matched': True, 'reason': 'exact-rpm-role', 'slot': exact[0]}

        rpm_candidates = [
            slot for slot in sample_slots
            if slot.get('rpm') is not None and (slot.get('role') == 'exhaust') == source_is_exhaust
        ]
        if rpm_candidates:
            best = min(rpm_candidates, key=lambda slot: abs(int(slot['rpm']) - source_rpm))
            return {'matched': True, 'reason': 'nearest-rpm-role', 'slot': best}

    role_candidates = [slot for slot in sample_slots if (slot.get('role') == 'exhaust') == source_is_exhaust]
    if role_candidates:
        return {'matched': True, 'reason': 'role-fallback', 'slot': role_candidates[0]}

    return {'matched': False, 'reason': 'unmatched', 'slot': None}


def prepare_engine_audio_workspace(templates_dir: str, display_names: Optional[Dict[str, str]] = None,
                                   output_root: Path = ENGINE_AUDIO_WORKSPACE,
                                   clone_roots: bool = True) -> Dict[str, Any]:
    asset_index = build_sound_asset_index()
    source_shortlist = load_engine_audio_source_shortlist()
    display_names = display_names or {}
    specs = load_template_specs(templates_dir, display_names)
    existing_overrides = load_engine_audio_overrides()
    overrides = dict(existing_overrides)
    manifest_entries: List[Dict[str, Any]] = []
    prepared = 0
    cloned_assets = 0

    for spec in specs:
        template_uasset = Path(templates_dir) / f'{spec.name}.uasset'
        if not template_uasset.is_file():
            continue
        override_row = overrides.get(spec.name) or {}
        template_sound_asset = primary_engine_sound_path(template_uasset)
        root_asset_path = template_sound_asset
        fallback_root_asset = str(override_row.get('vanilla_sound_asset') or '').strip()
        if not root_asset_path and fallback_root_asset:
            root_asset_path = fallback_root_asset
        if not root_asset_path:
            continue
        try:
            resolve_sound_asset_file(root_asset_path, asset_index)
        except KeyError:
            if not fallback_root_asset or fallback_root_asset == root_asset_path:
                continue
            try:
                resolve_sound_asset_file(fallback_root_asset, asset_index)
            except KeyError:
                continue
            root_asset_path = fallback_root_asset

        override_sound_dir = spec.asset_name
        target_root_asset_path = rewrite_sound_asset_path(root_asset_path, override_sound_dir)
        target_root_file = asset_path_to_output_file(MOD_SOUND_BASE, target_root_asset_path)
        clone_report = None
        if clone_roots:
            clone_report = clone_sound_family(root_asset_path, override_sound_dir, asset_index)
            cloned_assets += len(clone_report['copied_assets'])

        profile = inventory_sound_profile(root_asset_path, asset_index)
        workspace_dir = output_root / spec.name
        raw_dir = workspace_dir / 'raw'
        references_dir = workspace_dir / 'references'
        normalized_dir = workspace_dir / 'normalized'
        encoded_dir = workspace_dir / 'encoded'
        notes_dir = workspace_dir / 'notes'
        for path in (raw_dir, references_dir, normalized_dir, encoded_dir, notes_dir):
            path.mkdir(parents=True, exist_ok=True)

        metadata = {
            'engine_name': spec.name,
            'display_name': spec.display_name,
            'variant': spec.variant,
            'hp': spec.hp,
            'max_rpm': spec.max_rpm,
            'asset_name': spec.asset_name,
            'sound_profile': spec.sound_profile,
            'template_sound_asset': template_sound_asset,
            'vanilla_sound_asset': root_asset_path,
            'resolved_vanilla_sound_asset': profile.get('resolved_root_asset_path'),
            'override_sound_dir': override_sound_dir,
            'override_sound_asset': target_root_asset_path,
            'override_root_file': str(target_root_file),
            'status': 'vanilla-fallback-only',
            'reversible': True,
            'sample_slots': profile['sample_slots'],
            'slot_summary': {
                'count': len(profile['sample_slots']),
                'engine_slots': sum(1 for slot in profile['sample_slots'] if slot.get('role') == 'engine'),
                'exhaust_slots': sum(1 for slot in profile['sample_slots'] if slot.get('role') == 'exhaust'),
                'rpm_values': sorted({slot['rpm'] for slot in profile['sample_slots'] if slot.get('rpm') is not None}),
            },
            'paths': {
                'raw': str(raw_dir),
                'references': str(references_dir),
                'normalized': str(normalized_dir),
                'encoded': str(encoded_dir),
                'notes': str(notes_dir),
            },
            'candidate_sources': list(source_shortlist.get(spec.name, [])),
            'clone_report': clone_report,
        }
        (workspace_dir / 'profile.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        note_lines = [
            f'Engine: {spec.name}',
            f'Display name: {spec.display_name}',
            f'Vanilla sound asset: {root_asset_path}',
            f'Override sound asset: {target_root_asset_path}',
            '',
            'Drop source WAV files into raw/ using these slot names:',
        ]
        for slot in profile['sample_slots']:
            note_lines.append(
                f"- {slot['basename']}.wav ({slot['role']}, rpm={slot.get('rpm')}, target ~{slot.get('duration_hint_seconds', 0):.2f}s)"
            )
        candidate_sources = list(source_shortlist.get(spec.name, []))
        if candidate_sources:
            note_lines.extend([
                '',
                'Research shortlist for this engine:',
            ])
            for row in candidate_sources:
                label = str(row.get('label') or row.get('url') or 'source').strip()
                url = str(row.get('url') or '').strip()
                quality = str(row.get('quality_notes') or '').strip()
                rpm_cover = str(row.get('rpm_band_material') or '').strip()
                caution = str(row.get('reuse_caution') or '').strip()
                source_type = str(row.get('source_type') or '').strip()
                header = f"- {label}"
                if source_type:
                    header += f" [{source_type}]"
                if url:
                    header += f": {url}"
                note_lines.append(header)
                if quality:
                    note_lines.append(f"  quality: {quality}")
                if rpm_cover:
                    note_lines.append(f"  rpm coverage: {rpm_cover}")
                if caution:
                    note_lines.append(f"  caution: {caution}")
        note_lines.extend([
            '',
            'Downloaded/source-master references can be kept in references/.',
            'Only slot-ready WAVs that should map to the game assets belong in raw/.',
            '',
            'Normalized review files are written into normalized/.',
            'Externally encoded SoundWave triplets can be dropped into encoded/ as <basename>.uasset/.uexp/.ubulk.',
            'Use scripts/prepare_engine_audio_assets.py validate --engine <name> to check slot coverage.',
            'Use scripts/prepare_engine_audio_assets.py install-triplet --engine <name> --slot <basename> --source-uasset <path> to copy a pre-encoded triplet into the correct slot.',
            'Use scripts/prepare_engine_audio_assets.py unreal-cook --engine <name> to import normalized WAVs with Unreal and cook fresh SoundWave triplets into encoded/.',
            'The encoded/ folder stores encoded_manifest.json so cooked assets can be copied back into the mod tree without guessing their package path.',
            'Overrides stay disabled by default, so vanilla sounds remain active until you enable them.',
        ])
        (notes_dir / 'README.txt').write_text('\n'.join(note_lines) + '\n', encoding='utf-8')

        overrides.setdefault(spec.name, {
            'enabled': False,
            'override_sound_dir': override_sound_dir,
            'vanilla_sound_asset': root_asset_path,
            'override_sound_asset': target_root_asset_path,
            'variant': spec.variant,
            'sound_profile': spec.sound_profile,
            'asset_name': spec.asset_name,
            'reversible': True,
        })

        manifest_entries.append(metadata)
        prepared += 1

    save_engine_audio_overrides(overrides)
    AUDIO_WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    ENGINE_AUDIO_MANIFEST_PATH.write_text(
        json.dumps({
            'prepared_engines': prepared,
            'cloned_assets': cloned_assets,
            'clone_roots': bool(clone_roots),
            'engines': manifest_entries,
        }, indent=2),
        encoding='utf-8',
    )
    return {
        'prepared_engines': prepared,
        'cloned_assets': cloned_assets,
        'manifest_path': str(ENGINE_AUDIO_MANIFEST_PATH),
        'override_manifest_path': str(ENGINE_AUDIO_OVERRIDE_PATH),
    }


def load_engine_audio_workspace_profile(engine_name: str, workspace_root: Path = ENGINE_AUDIO_WORKSPACE) -> Dict[str, Any]:
    profile_path = workspace_root / engine_name / 'profile.json'
    return json.loads(profile_path.read_text(encoding='utf-8'))


def install_preencoded_triplet(engine_name: str, slot_basename: str, source_uasset: Path | str,
                               workspace_root: Path = ENGINE_AUDIO_WORKSPACE) -> Dict[str, Any]:
    profile = load_engine_audio_workspace_profile(engine_name, workspace_root=workspace_root)
    source_uasset = Path(source_uasset)
    if source_uasset.suffix.lower() != '.uasset':
        raise ValueError(f'Expected a .uasset source file, got: {source_uasset}')
    if not source_uasset.is_file():
        raise FileNotFoundError(source_uasset)

    slot_names = {str(slot.get('basename') or '').strip() for slot in profile.get('sample_slots', [])}
    if slot_basename not in slot_names:
        raise KeyError(f'Unknown slot for {engine_name}: {slot_basename}')

    encoded_dir = Path(profile['paths']['encoded'])
    encoded_dir.mkdir(parents=True, exist_ok=True)

    copied_files: List[str] = []
    for suffix in ('.uasset', '.uexp', '.ubulk'):
        src = source_uasset if suffix == '.uasset' else _require_sidecar(source_uasset, suffix)
        dst = encoded_dir / f'{slot_basename}{suffix}'
        shutil.copy2(src, dst)
        copied_files.append(str(dst))

    source_asset_path = _asset_path_from_uasset_file(source_uasset)
    if source_asset_path:
        update_encoded_workspace_manifest(
            engine_name,
            slot_basename,
            source_asset_path=source_asset_path,
            workspace_root=workspace_root,
        )

    return {
        'engine_name': engine_name,
        'slot_basename': slot_basename,
        'source_uasset': str(source_uasset),
        'encoded_dir': str(encoded_dir),
        'copied_files': copied_files,
    }


def validate_encoded_workspace(engine_name: str, workspace_root: Path = ENGINE_AUDIO_WORKSPACE) -> Dict[str, Any]:
    profile = load_engine_audio_workspace_profile(engine_name, workspace_root=workspace_root)
    encoded_dir = Path(profile['paths']['encoded'])
    required_suffixes = {'.uasset', '.uexp', '.ubulk'}
    available: Dict[str, set[str]] = {}

    if encoded_dir.is_dir():
        for path in sorted(encoded_dir.iterdir()):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in required_suffixes:
                continue
            available.setdefault(path.stem, set()).add(suffix)

    expected_slots = [str(slot.get('basename') or '').strip() for slot in profile.get('sample_slots', [])]
    slot_reports: List[Dict[str, Any]] = []
    ready_count = 0
    partial_count = 0

    for basename in expected_slots:
        present_suffixes = available.get(basename, set())
        missing_suffixes = sorted(required_suffixes - present_suffixes)
        if present_suffixes == required_suffixes:
            status = 'ready'
            ready_count += 1
        elif present_suffixes:
            status = 'partial'
            partial_count += 1
        else:
            status = 'missing'
        slot_reports.append({
            'basename': basename,
            'status': status,
            'present_files': sorted(present_suffixes),
            'missing_files': missing_suffixes,
        })

    expected_set = set(expected_slots)
    extra_assets: List[Dict[str, Any]] = []
    for basename, present_suffixes in sorted(available.items()):
        if basename in expected_set:
            continue
        extra_assets.append({
            'basename': basename,
            'status': 'ready' if present_suffixes == required_suffixes else 'partial',
            'present_files': sorted(present_suffixes),
            'missing_files': sorted(required_suffixes - present_suffixes),
        })

    return {
        'engine_name': engine_name,
        'encoded_dir': str(encoded_dir),
        'expected_slot_count': len(expected_slots),
        'ready_slot_count': ready_count,
        'partial_slot_count': partial_count,
        'missing_slot_count': len(expected_slots) - ready_count - partial_count,
        'extra_asset_count': len(extra_assets),
        'slots': slot_reports,
        'extra_assets': extra_assets,
    }


def normalize_engine_audio_workspace(engine_name: str, workspace_root: Path = ENGINE_AUDIO_WORKSPACE, *,
                                     target_sample_rate: int = _TARGET_SAMPLE_RATE_DEFAULT,
                                     target_channels: int = _TARGET_CHANNELS_DEFAULT,
                                     target_sample_width: int = _TARGET_SAMPLE_WIDTH_DEFAULT,
                                     target_duration_seconds: Optional[float] = None,
                                     peak_target: float = 0.92,
                                     fade_ms: int = _FADE_MS_DEFAULT,
                                     trim_silence: bool = True,
                                     silence_rms: int = 256) -> Dict[str, Any]:
    profile = load_engine_audio_workspace_profile(engine_name, workspace_root=workspace_root)
    workspace_dir = workspace_root / engine_name
    raw_dir = Path(profile['paths']['raw'])
    normalized_dir = Path(profile['paths']['normalized'])
    sample_slots = list(profile.get('sample_slots', []))

    source_files = sorted(raw_dir.rglob('*.wav'))
    outputs: List[Dict[str, Any]] = []
    unmatched_sources: List[str] = []

    for source_file in source_files:
        rel = source_file.relative_to(raw_dir)
        output_file = normalized_dir / rel.parent / f'{source_file.stem}_normalized{source_file.suffix}'
        duration_hint = target_duration_seconds
        if duration_hint is None:
            match = _match_sample_slot(source_file.stem, sample_slots)
            if match['slot'] is not None and match['slot'].get('rpm') is not None:
                duration_hint = recommended_sample_duration_seconds(source_file.stem, int(match['slot']['rpm']))
            else:
                duration_hint = recommended_sample_duration_seconds(source_file.stem)

        result = normalize_wav_source_file(
            source_file,
            output_file,
            target_sample_rate=target_sample_rate,
            target_channels=target_channels,
            target_sample_width=target_sample_width,
            target_duration_seconds=duration_hint,
            peak_target=peak_target,
            fade_ms=fade_ms,
            trim_silence=trim_silence,
            silence_rms=silence_rms,
        )
        match = _match_sample_slot(source_file.stem, sample_slots)
        if not match['matched']:
            unmatched_sources.append(source_file.name)
        outputs.append({
            'source_path': result['source_file'],
            'output_path': result['output_file'],
            'source_name': source_file.name,
            'output_name': output_file.name,
            'source': {
                'channels': result['source_channels'],
                'sample_rate': result['source_sample_rate'],
                'sample_width': result['source_sample_width'],
                'frame_count': result['source_frame_count'],
                'duration_seconds': result['source_duration_seconds'],
                'peak_before': result['peak_before'],
                'rms_before': result['rms_before'],
            },
            'output': {
                'channels': result['output_channels'],
                'sample_rate': result['output_sample_rate'],
                'sample_width': result['output_sample_width'],
                'frame_count': result['output_frame_count'],
                'duration_seconds': result['output_duration_seconds'],
                'peak_after': result['peak_after'],
                'rms_after': result['rms_after'],
            },
            'trim': result['trim'],
            'slot_match': {
                'matched': match['matched'],
                'reason': match['reason'],
                'asset_path': match['slot']['asset_path'] if match['slot'] else None,
                'rpm': match['slot']['rpm'] if match['slot'] else None,
                'role': match['slot']['role'] if match['slot'] else None,
            },
        })

    manifest = {
        'engine_name': engine_name,
        'workspace_dir': str(workspace_dir),
        'raw_dir': str(raw_dir),
        'normalized_dir': str(normalized_dir),
        'target_format': {
            'sample_rate': target_sample_rate,
            'channels': target_channels,
            'sample_width': target_sample_width,
            'target_duration_seconds': target_duration_seconds,
            'peak_target': peak_target,
            'fade_ms': fade_ms,
            'trim_silence': trim_silence,
            'silence_rms': silence_rms,
        },
        'input_count': len(source_files),
        'output_count': len(outputs),
        'unmatched_sources': unmatched_sources,
        'reversible': True,
        'fallback_mode': 'vanilla assets remain active until the override is enabled',
        'outputs': outputs,
    }
    write_json_manifest(workspace_dir / 'normalized_manifest.json', manifest)
    return manifest


def normalize_all_engine_audio_workspaces(workspace_root: Path = ENGINE_AUDIO_WORKSPACE, **kwargs: Any) -> Dict[str, Any]:
    summaries: List[Dict[str, Any]] = []
    for engine_name in discover_engine_audio_workspaces(workspace_root):
        summaries.append(normalize_engine_audio_workspace(engine_name, workspace_root=workspace_root, **kwargs))
    payload = {
        'workspace_root': str(workspace_root),
        'engine_count': len(summaries),
        'engines': summaries,
    }
    write_json_manifest(ENGINE_AUDIO_NORMALIZATION_MANIFEST_PATH, payload)
    return payload


def discover_engine_audio_workspaces(workspace_root: Path = ENGINE_AUDIO_WORKSPACE) -> List[str]:
    if not workspace_root.is_dir():
        return []
    names: List[str] = []
    for child in sorted(workspace_root.iterdir()):
        if child.is_dir() and (child / 'profile.json').is_file():
            names.append(child.name)
    return names
