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
from typing import Dict
from .utils.file_utils import download_single_file
from .utils.helper_utils import get_dynamic_buffer_size, verify_file_integrity, calculate_chunks_and_batches, check_disk_space
from .utils.exception_utils import DownloadError, NetworkError, StorageError
from .utils.network_utils import BandwidthMonitor


# Constants for configuration
CHUNK_READ_SIZE = 524288  # 512KB chunks
DEFAULT_BUFFER_SIZE = 8388608  # 8MB buffer, adjusts dynamically
MAX_CONNECTIONS = 150  # Increased concurrency for faster downloads
MMAP_THRESHOLD = 134217728  # Use mmap for files larger than 128MB
MAX_BATCH_SIZE = 8  # Max number of chunks per batch
MAX_RETRIES = 8  # Max number of retries for failed chunks
RETRY_DELAY = 2  # Base delay in seconds for exponential backoff

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


async def retry_chunk_download(session, url, start, end, chunk_file, progress=None, task_id=None):
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
                            if progress and task_id:
                                progress.update(task_id, advance=len(data))
                    return True

                # Handle specific status codes
                if response.status in {408, 429, 500, 502, 503, 504}:
                    delay = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    if progress:
                        progress.console.print(
                            f"[yellow]Chunk retry {attempt + 1}/{MAX_RETRIES}, waiting {delay}s...[/yellow]")
                    await asyncio.sleep(delay)
                    continue
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (2 ** attempt)
                if progress:
                    progress.console.print(
                        f"[yellow]Network error, retry {attempt + 1}/{MAX_RETRIES} in {delay}s: {str(e)}[/yellow]")
                await asyncio.sleep(delay)
                continue
            else:
                if progress:
                    progress.console.print(f"[red]Failed after {
                                           MAX_RETRIES} attempts[/red]")
                return False
    return False


async def download_chunk(session, url, start, end, chunk_file, progress=None, task_id=None):
    """Download a single chunk of the file with retry logic."""
    return await retry_chunk_download(session, url, start, end, chunk_file, progress, task_id)


async def merge_chunks(chunk_files, output_file, buffer_size, progress=None):
    """Merge downloaded chunks into the final output file."""
    total_size = sum(os.path.getsize(chunk) for chunk in chunk_files)
    task_id = None
    if progress:
        task_id = progress.add_task(
            "[yellow]Merging chunks...", total=total_size)

    async with aiofiles.open(output_file, 'wb') as out:
        for chunk_file in chunk_files:
            async with aiofiles.open(chunk_file, 'rb') as f:
                while chunk := await f.read(buffer_size):
                    await out.write(chunk)
                    if progress and task_id:
                        progress.update(task_id, advance=len(chunk))

    for chunk_file in chunk_files:
        os.remove(chunk_file)


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
        ssl=ssl.create_default_context(),
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

    # if os.getenv('HTTP_PROXY') or os.getenv('HTTPS_PROXY'):
    #     session_kwargs["proxy"] = os.getenv(
    #         'HTTP_PROXY') or os.getenv('HTTPS_PROXY')

    temp_dir = tempfile.mkdtemp(prefix="download_")
    bandwidth_monitor = BandwidthMonitor()

    try:
        async with aiohttp.ClientSession(**session_kwargs) as session:
            # Get file size and verify resources
            try:
                async with session.head(url) as response:
                    file_size = int(response.headers.get("Content-Length", 0))
                    accepts_ranges = response.headers.get(
                        "Accept-Ranges", "").lower() == "bytes"

                    # Check disk space
                    if not check_disk_space(file_size):
                        raise StorageError("Insufficient disk space")

                    if not accepts_ranges:
                        if progress:
                            progress.console.print(
                                "[yellow]Server doesn't support chunked downloads, trying single file...[/yellow]")
                            return await download_single_file(session, url, output_path, progress)
            except Exception as e:
                if progress:
                    progress.console.print(
                        f"[red]Failed to get file info: {str(e)}[/red]")
                return await download_single_file(session, url, output_path, progress)

            # Calculate chunks and prepare download
            chunks, batch_size = calculate_chunks_and_batches(file_size)
            buffer_size = get_dynamic_buffer_size(file_size)
            chunk_files = [os.path.join(temp_dir, f"{output_path}.part{i}")
                           for i in range(len(chunks))]

            # Process chunks in batches
            for batch_start in range(0, len(chunks), batch_size):
                batch_end = min(batch_start + batch_size, len(chunks))
                batch_chunks = chunks[batch_start:batch_end]
                batch_files = chunk_files[batch_start:batch_end]

                tasks = []
                for idx, (start, end) in enumerate(batch_chunks):
                    task_id = None
                    if progress:
                        task_id = progress.add_task(
                            f"Chunk {batch_start + idx + 1}/{len(chunks)}",
                            total=end - start + 1
                        )
                    tasks.append(download_chunk(
                        session, url, start, end, batch_files[idx], progress, task_id))

                # Execute batch with handling for failed chunks
                results = await asyncio.gather(*tasks, return_exceptions=True)
                failed_chunks = [
                    i for i, res in enumerate(results) if not res]

                if failed_chunks:
                    if progress:
                        progress.console.print(
                            f"[yellow]Retrying {len(failed_chunks)} failed chunks...[/yellow]")

                    # Retry failed chunks
                    for chunk_idx in failed_chunks:
                        start, end = batch_chunks[chunk_idx]
                        success = await retry_chunk_download(
                            session, url, start, end,
                            batch_files[chunk_idx], progress,
                            progress.add_task(
                                f"Retry Chunk {batch_start + chunk_idx + 1}")
                        )
                        if not success:
                            if progress:
                                progress.console.print(
                                    "[red]Chunk retry failed, attempting to resume...[/red]")
                            try:
                                # Try to resume download
                                if await resume_download(session, url, output_path, start, progress):
                                    continue
                            except NetworkError:
                                if progress:
                                    progress.console.print(
                                        "[red]Resume failed, falling back to single file...[/red]")
                                return await download_single_file(session, url, output_path, progress)

                # Log transfer for bandwidth monitoring
                for batch_file in batch_files:
                    if os.path.exists(batch_file):
                        bandwidth_monitor.log_transfer(
                            os.path.getsize(batch_file))

            # Merge chunks into final output file
            await merge_chunks(chunk_files, output_path, buffer_size, progress)

            # Verify file integrity
            if not await verify_file_integrity(output_path, CHUNK_READ_SIZE):
                raise DownloadError("File integrity check failed")

            if progress:
                speed = bandwidth_monitor.get_speed()
                progress.console.print(
                    f"[bold green]Download completed: {output_path} "
                    f"(Avg. Speed: {humanize.naturalsize(
                        speed)}/s)[/bold green]"
                )
            return True

    except aiohttp.ClientError as e:
        if progress:
            progress.console.print(f"[red]Network error: {str(e)}[/red]")
        raise NetworkError(str(e))
    except IOError as e:
        if progress:
            progress.console.print(f"[red]Storage error: {str(e)}[/red]")
        raise StorageError(str(e))
    except Exception as e:
        if progress:
            progress.console.print(f"[red]Download failed: {str(e)}[/red]")
        return await download_single_file(session, url, output_path, progress)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
