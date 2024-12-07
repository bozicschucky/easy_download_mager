import aiohttp
from aiohttp import ClientTimeout, TCPConnector
import asyncio
import os
from pathlib import Path
import aiofiles
import humanize
import shutil
from concurrent.futures import ThreadPoolExecutor
import tempfile
import ssl
import certifi
from typing import Dict
from utils.file_utils import download_single_file
from utils.helper_utils import get_dynamic_buffer_size, verify_file_integrity, calculate_chunks_and_batches, check_disk_space
from utils.exception_utils import DownloadError, NetworkError, StorageError
from utils.network_utils import BandwidthMonitor
from logger.progress_tracker import ProgressTracker, logger


# Constants for configuration
CHUNK_READ_SIZE = 524288  # 512KB chunks
DEFAULT_BUFFER_SIZE = 8388608  # 8MB buffer, adjusts dynamically
MAX_CONNECTIONS = 150  # Increased concurrency for faster downloads
MMAP_THRESHOLD = 134217728  # Use mmap for files larger than 128MB
MAX_BATCH_SIZE = 8  # Max number of chunks per batch
MAX_RETRIES = 8  # Max number of retries for failed chunks
RETRY_DELAY = 2  # Base delay in seconds for exponential backoff

ssl_context = ssl.create_default_context(cafile=certifi.where())
chunk_cache: Dict[str, bytes] = {}
file_handle_pool = ThreadPoolExecutor(max_workers=32)


def get_default_downloads_dir() -> str:
    """Get the default downloads directory for the current platform"""
    return str(Path.home() / "Downloads")

async def resume_download(session, url: str, output_file: str, start_byte: int, progress=None):
    """Resume download from specific byte position"""
    headers = {'Range': f'bytes={start_byte}-'}

    async with session.get(url, headers=headers) as response:
        if response.status != 206:
            raise NetworkError("Server doesn't support resume")

        async with aiofiles.open(output_file, 'ab') as f:
            async for data in response.content.iter_chunked(CHUNK_READ_SIZE):
                await f.write(data)
                if progress:
                    progress.advance(len(data))
    return True


async def retry_chunk_download(session, url, start, end, chunk_file, progress_tracker):
    """Retry downloading a chunk with exponential backoff"""
    for attempt in range(MAX_RETRIES):
        try:
            headers = {"Range": f"bytes={start}-{end}"}
            async with session.get(url, headers=headers) as response:
                if response.status == 206:  # Partial content success
                    async with aiofiles.open(chunk_file, "wb") as f:
                        total = 0
                        async for data in response.content.iter_chunked(CHUNK_READ_SIZE):
                            await f.write(data)
                            total += len(data)
                            if progress_tracker:
                                progress_tracker.update(len(data))
                    return True

                # Handle specific status codes
                if response.status in {408, 429, 500, 502, 503, 504}:
                    delay = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Chunk retry {attempt + 1}/{MAX_RETRIES}, waiting {delay}s due to status {response.status}...")
                    await asyncio.sleep(delay)
                    continue
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (2 ** attempt)
                if progress_tracker:
                    progress_tracker.log_message(
                        f"Network error, retry {attempt + 1}/{MAX_RETRIES} in {delay}s: {str(e)}")
                await asyncio.sleep(delay)
                continue
            else:
                if progress_tracker:
                    progress_tracker.log_message(
                        f"Failed after {MAX_RETRIES} attempts: {str(e)}")
                return False
    return False


async def download_chunk(session, url, start, end, output_file, progress_tracker=None):
    headers = {'Range': f'bytes={start}-{end}'}
    try:
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            async with aiofiles.open(output_file, 'wb') as f:
                async for chunk in resp.content.iter_chunked(8192):
                    await f.write(chunk)
                    if progress_tracker:
                        progress_tracker.update(len(chunk))
        return True
    except Exception as e:
        logger.error(f"Chunk download failed: {str(e)}")
        return False


async def merge_chunks(chunk_files, output_file, buffer_size, progress_tracker=None):
    """Merge downloaded chunks into the final output file."""
    total_size = sum(os.path.getsize(chunk) for chunk in chunk_files)
    logger.success(f"Merging chunks into {os.path.basename(output_file)} {
                humanize.naturalsize(total_size)}")

    async with aiofiles.open(output_file, 'wb') as out:
        for chunk_file in chunk_files:
            async with aiofiles.open(chunk_file, 'rb') as f:
                while True:
                    chunk = await f.read(buffer_size)
                    if not chunk:
                        break
                    await out.write(chunk)
                    if progress_tracker:
                        progress_tracker.update(len(chunk))

    for chunk_file in chunk_files:
        os.remove(chunk_file)

    logger.success(f"Completed merging {os.path.basename(output_file)}")


async def download_file(url: str, output_file: str, output_dir: str = None, progress=None):
    """
    Download file with optional output directory
    Args:
        url: Source URL
        output_file: Target filename
        output_dir: Optional custom output directory (default: user's Downloads folder)
        progress: Progress callback
    """

    # Resolve output directory
    output_dir = output_dir or get_default_downloads_dir()
    os.makedirs(output_dir, exist_ok=True)

    # Combine output path
    output_path = os.path.join(output_dir, output_file)

    connector = TCPConnector(
        limit=MAX_CONNECTIONS,
        ssl=ssl_context,
        verify_ssl=True,
        ttl_dns_cache=300,
        enable_cleanup_closed=True
    )

    timeout = ClientTimeout(total=3600, connect=60)
    session_kwargs = {
        "connector": connector,
        "timeout": timeout,
        "headers": {
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }
    }

    temp_dir = tempfile.mkdtemp(prefix="download_")
    bandwidth_monitor = BandwidthMonitor()

    try:
        async with aiohttp.ClientSession(**session_kwargs) as session:
            # Get file size and check server support
            async with session.head(url) as response:
                file_size = int(response.headers.get("Content-Length", 0))
                accepts_ranges = response.headers.get(
                    "Accept-Ranges", "").lower() == "bytes"

                # Check disk space
                if not check_disk_space(file_size):
                    raise StorageError("Insufficient disk space")

                if not accepts_ranges:
                    logger.info(
                        "Server doesn't support chunked downloads, trying single file...")
                    return await download_single_file(session, url, CHUNK_READ_SIZE, output_path, progress)

                # Set up progress tracker
                progress_tracker = ProgressTracker(file_size)

            # Calculate chunks and prepare download
            chunks, batch_size = calculate_chunks_and_batches(file_size)
            buffer_size = get_dynamic_buffer_size(file_size)
            chunk_files = [os.path.join(temp_dir, f"{output_file}.part{
                                        i}") for i in range(len(chunks))]

            # Process chunks in batches
            for batch_num, batch_start in enumerate(range(0, len(chunks), batch_size), start=1):
                batch_end = min(batch_start + batch_size, len(chunks))
                batch_chunks = chunks[batch_start:batch_end]
                batch_files = chunk_files[batch_start:batch_end]

                logger.success(f"Starting Batch {
                            batch_num}/{(len(chunks) + batch_size - 1) // batch_size}")

                tasks = []
                for idx, (start, end) in enumerate(batch_chunks):
                    tasks.append(download_chunk(
                        session, url, start, end, batch_files[idx], progress_tracker
                    ))

                # Execute batch and handle results
                results = await asyncio.gather(*tasks, return_exceptions=True)
                failed_chunks = [i for i, res in enumerate(results) if not res]

                if failed_chunks:
                    logger.warning(
                        f"Retrying {len(failed_chunks)} failed chunks...")

                    # Retry failed chunks
                    for chunk_idx in failed_chunks:
                        start, end = batch_chunks[chunk_idx]
                        success = await retry_chunk_download(
                            session, url, start, end, batch_files[chunk_idx], progress_tracker
                        )
                        if not success:
                            logger.error(
                                "Chunk retry failed, attempting to resume...")
                            try:
                                # Try to resume download
                                if await resume_download(session, url, output_path, start, progress_tracker):
                                    continue
                            except NetworkError:
                                logger.error(
                                    "Resume failed, falling back to single file...")
                                return await download_single_file(session, url, CHUNK_READ_SIZE, output_path, progress)

                # Log transfer for bandwidth monitoring
                for batch_file in batch_files:
                    if os.path.exists(batch_file):
                        bandwidth_monitor.log_transfer(
                            os.path.getsize(batch_file))

            # Merge chunks into final output file
            await merge_chunks(chunk_files, output_path, buffer_size, progress_tracker)

            # Verify file integrity
            if not await verify_file_integrity(output_path, CHUNK_READ_SIZE):
                raise DownloadError("File integrity check failed")

            logger.success(f"Download completed: {output_path} (Avg. Speed: {
                        bandwidth_monitor.get_speed() / (1024 * 1024):.1f} MB/s)")

    except aiohttp.ClientError as e:
        logger.error(f"Network error: {str(e)}")
        raise NetworkError(str(e))
    except IOError as e:
        logger.error(f"Storage error: {str(e)}")
        raise StorageError(str(e))
    except ssl.SSLError as e:
        logger.error(f"SSL error: {e}")
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return await download_single_file(session, url, CHUNK_READ_SIZE, output_path, progress)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
