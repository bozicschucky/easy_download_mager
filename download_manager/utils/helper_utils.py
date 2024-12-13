from functools import lru_cache
import hashlib
import math
import os
import re
import shutil
from typing import List, Optional, Tuple
from urllib.parse import unquote
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


def sanitize_filename(filename: str) -> str:
    """
    Clean filename by:
    1. Decode URL encoding (%20 etc)
    2. Remove invalid characters
    3. Replace spaces properly
    4. Preserve file extension
    """
    # First decode URL encoded characters
    filename = unquote(filename)

    # Split filename and extension
    name, ext = os.path.splitext(filename)
    name = re.sub(r'[<>:"/\\|?*]', '', name)  # Remove Windows invalid chars
    name = re.sub(r'\s+', ' ', name)          # Normalize spaces
    name = name.strip('. ')
    clean_filename = name + ext

    return clean_filename


def extract_filename_from_url(url: str) -> str:
    """
    Extract clean filename from URL, handling complex paths and encoded characters.
    Example:
    Input: http:some_url/AudioBooks/Olaf Stapledon/1944 - Sirius/Sirius 09.mp3
    Output: Sirius 09.mp3
    """
    # First decode URL encoded characters
    decoded_url = unquote(url)

    # Get the path part and split into components
    path_parts = decoded_url.split('/')
    raw_filename = next((part for part in reversed(path_parts) if part), '')

    # If filename contains path-like sections, split and get last part
    if '{' in raw_filename:
        raw_filename = raw_filename.split('{')[0].strip()

    # Handle timestamp/date patterns in filename
    raw_filename = re.sub(r'\d{2,4}.*?(?=\S+\.\w+$)', '', raw_filename)
    clean_filename = sanitize_filename(raw_filename)

    return clean_filename.strip()
