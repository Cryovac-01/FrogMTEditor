"""
Pure-Python UE4/UE5 pak v8 writer (no external dependencies).

Verified format from Motor Town (UE5.5) pak files:
  - Version 8, uncompressed (Store), unencrypted
  - Per-file record header: 53 bytes
  - Footer: 221 bytes (magic at EOF-204)

Layout:
  [data section]
    For each file:
      [53-byte record header][raw file bytes]
  [index section]
    FString mount_point ("../../../")
    int32 file_count
    For each file:
      FString relative_path
      int64 absolute_offset  (to record header)
      int64 compressed_size
      int64 uncompressed_size
      uint32 compression_method (0=Store)
      u8[20] sha1
      uint8 flags (0)           (no block_count for Store/uncompressed)
      uint32 block_size (0)
  [footer: 221 bytes]
    u8[16] enc_key_guid (zeros)
    uint8 encrypted (0)
    uint32 magic = 0x5A6F12E1
    uint32 version = 8
    int64 index_offset
    int64 index_size
    u8[20] index_sha1
    u8[160] compression_names (zeros, 5 * 32 bytes)
"""
import hashlib
import os
import struct


_MAGIC = 0x5A6F12E1
_VERSION = 8
_MOUNT_POINT = '../../../'
_RECORD_HDR_SIZE = 53  # verified from parsing FF2000_P.pak


def _fstring(text: str) -> bytes:
    """Encode a UE FString: int32(len) + ascii_bytes + null."""
    enc = text.encode('ascii') + b'\x00'
    return struct.pack('<i', len(enc)) + enc


def _record_header(csize: int, sha1: bytes) -> bytes:
    """Build the 53-byte per-file record header."""
    return (
        struct.pack('<q', 0)        # offset_field = 0 (data follows immediately)
        + struct.pack('<q', csize)  # compressed_size
        + struct.pack('<q', csize)  # uncompressed_size (same — no compression)
        + struct.pack('<I', 0)      # compression_method = Store
        + sha1                      # 20 bytes
        + struct.pack('<B', 0)      # flags (not encrypted)
        + struct.pack('<I', 0)      # block_size
    )


def _index_entry(rel_path: str, offset: int, csize: int, sha1: bytes) -> bytes:
    """Build one index entry.

    UE only serializes the compression-blocks TArray when CompressionMethod != None.
    For Store (uncompressed) files that field is skipped entirely — matching the
    verified 53-byte record header layout: sha1 → bEncrypted → CompressionBlockSize.
    """
    return (
        _fstring(rel_path)
        + struct.pack('<q', offset)  # absolute offset to record header
        + struct.pack('<q', csize)   # compressed_size
        + struct.pack('<q', csize)   # uncompressed_size
        + struct.pack('<I', 0)       # compression_method = Store (0)
        + sha1                       # 20 bytes
        # block_count NOT written — UE skips TArray for CompressionMethod=None
        + struct.pack('<B', 0)       # bEncrypted = 0
        + struct.pack('<I', 0)       # CompressionBlockSize = 0
    )


def write_pak(source_dir: str, output_path: str) -> dict:
    """Pack all files under source_dir into a UE4/UE5 pak v8 file.

    Files are stored uncompressed and unencrypted.  Relative paths are
    computed from the *parent* of source_dir so that the directory name
    (e.g. 'Frogtuning718') is preserved at the root of the pak.

    Args:
        source_dir:  Root directory to pack (e.g. .../Frogtuning718).
        output_path: Destination .pak file path (created/overwritten).

    Returns:
        {'file_count': int, 'pak_size': int}
    """
    parent = os.path.dirname(os.path.abspath(source_dir))

    # Collect all files, sorted for determinism
    file_list = []
    for root, dirs, files in os.walk(source_dir):
        dirs.sort()
        for fname in sorted(files):
            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, parent).replace('\\', '/')
            file_list.append((rel_path, abs_path))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    index_entries = []

    with open(output_path, 'wb') as out:
        # ── Data section ──
        for rel_path, abs_path in file_list:
            with open(abs_path, 'rb') as f:
                file_data = f.read()

            sha1 = hashlib.sha1(file_data).digest()
            csize = len(file_data)
            record_offset = out.tell()

            out.write(_record_header(csize, sha1))
            out.write(file_data)

            index_entries.append((rel_path, record_offset, csize, sha1))

        # ── Index section ──
        index_offset = out.tell()

        index_buf = bytearray()
        index_buf += _fstring(_MOUNT_POINT)
        index_buf += struct.pack('<i', len(index_entries))
        for rel_path, offset, csize, sha1 in index_entries:
            index_buf += _index_entry(rel_path, offset, csize, sha1)
        index_bytes = bytes(index_buf)

        out.write(index_bytes)

        # ── Footer ──
        index_sha1 = hashlib.sha1(index_bytes).digest()

        footer = bytearray()
        footer += b'\x00' * 16                    # enc_key_guid
        footer += struct.pack('<B', 0)             # encrypted
        footer += struct.pack('<I', _MAGIC)
        footer += struct.pack('<I', _VERSION)
        footer += struct.pack('<q', index_offset)
        footer += struct.pack('<q', len(index_bytes))
        footer += index_sha1                       # 20 bytes
        footer += b'\x00' * 160                   # compression_names (5 × 32)
        out.write(bytes(footer))

    pak_size = os.path.getsize(output_path)
    return {'file_count': len(file_list), 'pak_size': pak_size}

