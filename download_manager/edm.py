import os
import aiohttp
import aiofiles
import asyncio
import tempfile
import shutil
import ssl
from aiohttp import ClientTimeout, TCPConnector
from functools import lru_cache
import math
import psutil

from download_manager.logger.progress_tracker import ProgressTracker


class EDM:
    @staticmethod
    @lru_cache(maxsize=32)
    def calculate_chunks_and_batches(file_size: int):
        """
        Calculate chunks and batch size based on file size using logarithmic scaling.
        """
        size_in_mb = file_size / (1024 * 1024)
        if size_in_mb <= 0:
            return [(0, file_size - 1)], 1

        # Max 64 chunks
        num_chunks = max(1, min(64, int(math.log2(size_in_mb)) + 1))
        chunk_size = file_size // num_chunks
        if file_size % num_chunks != 0:
            chunk_size += 1

        chunks = [
            (i * chunk_size, min(file_size - 1, (i + 1) * chunk_size - 1))
            for i in range(num_chunks)
        ]
        batch_size = max(1, int(math.log2(num_chunks)) + 1)
        return chunks, batch_size

    @staticmethod
    def get_dynamic_buffer_size(file_size: int, default_buffer_size=8 * 1024 * 1024) -> int:
        """Adjust the buffer size dynamically based on file size and system memory."""
        memory = psutil.virtual_memory()
        if file_size > 1024 * 1024 * 1024:  # Files >1GB
            # Max 16MB buffer
            return min(memory.available // 32, 16 * 1024 * 1024)
        return default_buffer_size

    @staticmethod
    async def download_file(
        url: str,
        output_file: str,
        output_dir: str = None,
        update_callback=None,
        download_id=None
    ):
        """
        Download file with dynamic chunking, retries, and error handling.
        """
        output_dir = output_dir or os.path.join(
            os.path.expanduser('~'), 'Downloads')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, output_file)

        ssl_context = ssl.create_default_context()
        connector = TCPConnector(
            limit=10,
            ssl=ssl_context,
            ttl_dns_cache=300,
            enable_cleanup_closed=True
        )

        timeout = ClientTimeout(total=3600, connect=60)
        session_kwargs = {
            "connector": connector,
            "timeout": timeout,
            "headers": {
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "User-Agent": "Mozilla/5.0"
            }
        }

        temp_dir = tempfile.mkdtemp(prefix="download_")

        try:
            async with aiohttp.ClientSession(**session_kwargs) as session:
                # Get file size and check server support
                async with session.head(url) as response:
                    file_size = int(response.headers.get("Content-Length", 0))
                    accepts_ranges = 'bytes' in response.headers.get(
                        "Accept-Ranges", "").lower()

                # Notify download start
                if update_callback and download_id:
                    await update_callback(
                        download_id=download_id,
                        status='started',
                        progress=0,
                        error=None
                    )

                if not accepts_ranges or file_size == 0:
                    # Fall back to single-file download
                    await EDM._download_single_file(session, url, output_path, update_callback, download_id)
                else:
                    # Calculate chunks and batch size using logarithmic scaling
                    chunks, batch_size = EDM.calculate_chunks_and_batches(
                        file_size)
                    buffer_size = EDM.get_dynamic_buffer_size(file_size)

                    # Proceed with chunked download
                    await EDM._download_with_chunks(
                        session, url, output_path, file_size, temp_dir,
                        chunks, batch_size, buffer_size, update_callback, download_id
                    )

            # Clean up temporary directory
            shutil.rmtree(temp_dir, ignore_errors=True)

            return True
        except Exception as e:
            # Notify failure
            if update_callback and download_id:
                await update_callback(
                    download_id=download_id,
                    status='failed',
                    progress=0,
                    error=str(e)
                )
            raise e

    @staticmethod
    async def _download_single_file(session, url, output_path, update_callback, download_id):
        """
        Download the file as a single chunk.
        """
        async with session.get(url) as response:
            response.raise_for_status()
            total_size = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            chunk_size = 32 * 1024  # 32KB

            async with aiofiles.open(output_path, 'wb') as f:
                async for chunk in response.content.iter_chunked(chunk_size):
                    await f.write(chunk)
                    downloaded += len(chunk)
                    progress = int(downloaded / total_size *
                                   100) if total_size else 0

                    # Update progress
                    if update_callback and download_id:
                        await update_callback(
                            download_id=download_id,
                            status='downloading',
                            progress=progress,
                            error=None
                        )
        # Notify completion
        if update_callback and download_id:
            await update_callback(
                download_id=download_id,
                status='completed',
                progress=100,
                error=None
            )

    @staticmethod
    async def _download_with_chunks(
        session, url, output_path, file_size, temp_dir,
        chunks, batch_size, buffer_size, update_callback, download_id
    ):
        """
        Download the file in chunks with retries and error handling.
        """
        chunk_files = [os.path.join(
            temp_dir, f"chunk_{i}") for i in range(len(chunks))]

        progress_tracker = ProgressTracker(file_size)

        # Set update callback for progress tracker if provided
        if update_callback and download_id:
            progress_tracker.set_update_callback(
                update_callback, download_id, url, output_path)

        for batch_start in range(0, len(chunks), batch_size):
            batch_end = min(batch_start + batch_size, len(chunks))
            batch_chunks = chunks[batch_start:batch_end]
            batch_files = chunk_files[batch_start:batch_end]

            tasks = []
            for idx, (start, end) in enumerate(batch_chunks):
                tasks.append(EDM._download_chunk(
                    session, url, start, end, batch_files[idx],
                    progress_tracker
                ))

            # Download chunks with retries
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                results = await asyncio.gather(*tasks, return_exceptions=True)
                # Check for failed tasks
                failed_indices = [i for i, res in enumerate(
                    results) if isinstance(res, Exception)]
                if not failed_indices:
                    break  # All chunks downloaded successfully

                if attempt < max_retries:
                    # Retry failed chunks
                    tasks = [
                        EDM._download_chunk(
                            session, url,
                            batch_chunks[i][0],
                            batch_chunks[i][1],
                            batch_files[i],
                            progress_tracker
                        )
                        for i in failed_indices
                    ]
                else:
                    # Exceeded max retries
                    raise Exception(
                        'Failed to download some chunks after retries')

        # Merge chunks
        await EDM._merge_chunks(chunk_files, output_path, buffer_size)

        # Notify completion
        if update_callback and download_id:
            await update_callback(
                download_id=download_id,
                status='completed',
                progress=100,
                error=None
            )

    @staticmethod
    async def _download_chunk(session, url, start, end, chunk_file, progress_tracker):
        """
        Download a single chunk of the file.
        """
        headers = {'Range': f'bytes={start}-{end}'}
        async with session.get(url, headers=headers) as response:
            response.raise_for_status()
            chunk_size = 32 * 1024  # 32KB
            downloaded = 0

            async with aiofiles.open(chunk_file, 'wb') as f:
                async for chunk in response.content.iter_chunked(chunk_size):
                    await f.write(chunk)
                    downloaded += len(chunk)
                    progress_tracker.update(downloaded)

    @staticmethod
    async def _merge_chunks(chunk_files, output_path, buffer_size):
        """
        Merge all chunk files into the final output file.
        """
        async with aiofiles.open(output_path, 'wb') as outfile:
            for chunk_file in chunk_files:
                async with aiofiles.open(chunk_file, 'rb') as infile:
                    while True:
                        data = await infile.read(buffer_size)
                        if not data:
                            break
                        await outfile.write(data)
                # Remove chunk file after merging
                os.remove(chunk_file)
