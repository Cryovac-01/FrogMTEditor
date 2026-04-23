"""
Pure-Python UE4/UE5 pak v8 reader (no external dependencies).

Reads the same format that pak_writer.py produces:
  - Version 8, uncompressed (Store), unencrypted
  - Per-file record header: 53 bytes
  - Footer: 221 bytes (magic at EOF-204)

See pak_writer.py docstring for full binary layout.
"""
import hashlib
import os
import struct


_MAGIC = 0x5A6F12E1
_FOOTER_SIZE = 221
_RECORD_HDR_SIZE = 53


def _read_fstring(data: bytes, offset: int) -> tuple:
    """Read a UE FString at offset. Returns (text, bytes_consumed)."""
    slen = struct.unpack_from('<i', data, offset)[0]
    if slen <= 0:
        return ('', 4)
    text = data[offset + 4:offset + 4 + slen - 1].decode('ascii', errors='replace')
    return (text, 4 + slen)


def read_pak(pak_path: str) -> dict:
    """Parse a UE4/UE5 v8 pak and return file entries with data.

    Args:
        pak_path: Path to the .pak file.

    Returns:
        {
            'mount_point': str,
            'file_count': int,
            'entries': [
                {
                    'path': str,        # relative path inside pak
                    'offset': int,      # absolute offset of record header
                    'size': int,        # uncompressed file size
                    'sha1': bytes,      # 20-byte SHA1 from index
                    'data': bytes,      # raw file content
                },
                ...
            ]
        }
    """
    file_size = os.path.getsize(pak_path)
    if file_size < _FOOTER_SIZE:
        raise ValueError(f'File too small to be a pak: {file_size} bytes')

    with open(pak_path, 'rb') as f:
        # ── Read footer (last 221 bytes) ──
        f.seek(file_size - _FOOTER_SIZE)
        footer = f.read(_FOOTER_SIZE)

        # Parse footer fields
        off = 0
        _enc_key_guid = footer[off:off + 16]; off += 16
        _encrypted = footer[off]; off += 1
        magic = struct.unpack_from('<I', footer, off)[0]; off += 4
        version = struct.unpack_from('<I', footer, off)[0]; off += 4
        index_offset = struct.unpack_from('<q', footer, off)[0]; off += 8
        index_size = struct.unpack_from('<q', footer, off)[0]; off += 8
        index_sha1 = footer[off:off + 20]; off += 20
        # remaining 160 bytes = compression_names (ignored)

        if magic != _MAGIC:
            raise ValueError(f'Bad magic: 0x{magic:08X} (expected 0x{_MAGIC:08X})')
        if version != 8:
            raise ValueError(f'Unsupported pak version: {version}')

        # ── Read index section ──
        f.seek(index_offset)
        index_data = f.read(index_size)

        # Verify index SHA1
        computed_sha1 = hashlib.sha1(index_data).digest()
        if computed_sha1 != index_sha1:
            raise ValueError('Index SHA1 mismatch')

        # Parse index
        idx = 0
        mount_point, consumed = _read_fstring(index_data, idx)
        idx += consumed

        file_count = struct.unpack_from('<i', index_data, idx)[0]
        idx += 4

        entries = []
        for _ in range(file_count):
            # FString path
            path, consumed = _read_fstring(index_data, idx)
            idx += consumed

            # Entry fields (no block_count for Store/uncompressed)
            rec_offset = struct.unpack_from('<q', index_data, idx)[0]; idx += 8
            csize = struct.unpack_from('<q', index_data, idx)[0]; idx += 8
            usize = struct.unpack_from('<q', index_data, idx)[0]; idx += 8
            comp = struct.unpack_from('<I', index_data, idx)[0]; idx += 4
            sha1 = index_data[idx:idx + 20]; idx += 20
            flags = index_data[idx]; idx += 1
            blocksize = struct.unpack_from('<I', index_data, idx)[0]; idx += 4

            entries.append({
                'path': path,
                'offset': rec_offset,
                'size': usize,
                'comp': comp,
                'sha1': sha1,
            })

        # ── Read file data ──
        for entry in entries:
            f.seek(entry['offset'] + _RECORD_HDR_SIZE)
            entry['data'] = f.read(entry['size'])

    return {
        'mount_point': mount_point,
        'file_count': file_count,
        'entries': entries,
    }


def extract_file(pak_path: str, internal_path: str) -> bytes:
    """Extract a single file from a pak by its internal path.

    Args:
        pak_path: Path to the .pak file.
        internal_path: Path inside the pak (e.g. 'MotorTown/Content/...')

    Returns:
        Raw file bytes, or raises KeyError if not found.
    """
    result = read_pak(pak_path)
    for entry in result['entries']:
        if entry['path'] == internal_path:
            return entry['data']
    raise KeyError(f'File not found in pak: {internal_path}')


def extract_to_dir(pak_path: str, output_dir: str) -> int:
    """Extract all files from a pak to a directory.

    Returns the number of files extracted.
    """
    result = read_pak(pak_path)
    for entry in result['entries']:
        out_path = os.path.join(output_dir, entry['path'].replace('/', os.sep))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'wb') as f:
            f.write(entry['data'])
    return len(result['entries'])
