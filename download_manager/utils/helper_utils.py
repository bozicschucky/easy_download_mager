from functools import lru_cache
import hashlib
import math
import shutil
from typing import List, Optional, Tuple
import aiofiles
import psutil


async def verify_file_integrity(file_path: str, chunk_size: int, expected_hash: Optional[str] = None) -> bool:
    """Verify downloaded file integrity using SHA-256"""
    hash_sha256 = hashlib.sha256()
    async with aiofiles.open(file_path, 'rb') as f:
        while chunk := await f.read(chunk_size):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest() == expected_hash if expected_hash else True


def check_disk_space(required_bytes: int, path: str = '.') -> bool:
    """Check if sufficient disk space is available"""
    free_space = shutil.disk_usage(path).free
    return free_space > required_bytes * 1.5  # 50% buffer


@lru_cache(maxsize=32)
def calculate_chunks_and_batches(file_size: int) -> Tuple[List[Tuple[int, int]], int]:
    """
    Calculate chunks and batch size based on file size.
    The number of chunks is determined using logarithmic scaling.
    """
    size_in_mb = file_size / (1024 * 1024)
    if size_in_mb <= 0:
        return [(0, file_size - 1)], 1

    # Max 64 chunks
    num_chunks = max(1, min(64, int(math.log2(size_in_mb)) + 1))
    chunk_size = file_size // num_chunks
    if file_size % num_chunks != 0:
        chunk_size += 1

    chunks = [(i * chunk_size, min(file_size - 1, (i + 1) * chunk_size - 1))
              for i in range(num_chunks)]
    batch_size = max(1, int(math.log2(num_chunks)) + 1)
    return chunks, batch_size


def get_dynamic_buffer_size(file_size: int, default_buffer_size=8388608) -> int:
    """Adjust the buffer size dynamically based on file size and system memory."""
    memory = psutil.virtual_memory()
    if file_size > 1024 * 1024 * 1024:  # Files >1GB
        return min(memory.available // 32, 16 * 1024 * 1024)  # Max 16MB buffer
    return default_buffer_size
