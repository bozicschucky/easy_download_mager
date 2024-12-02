import math
import time
import aiohttp
from aiohttp import ClientTimeout, TCPConnector
import asyncio
import os
import humanize


CHUNK_READ_SIZE = 65536  # 64KB chunks
BUFFER_SIZE = 16 * 1024 * 1024  # 16MB buffer
MAX_CHUNKS = 32
MAX_CONNECTIONS = 100
MAX_RETRIES = 8
MAX_WAIT_TIME = 120
BATCH_SIZE = 8  # Number of chunks to process in each batch


async def retry_failed_chunks(session, url, output_file, chunks, failed_indices, progress=None, max_retries=3):
    """Retry downloading failed chunks with exponential backoff"""
    remaining_chunks = failed_indices.copy()
    retry_attempt = 0

    while remaining_chunks and retry_attempt < max_retries:
        retry_attempt += 1
        if progress:
            progress.console.print(
                f"""[yellow]Retrying {len(remaining_chunks)} failed chunks (attempt {
                    retry_attempt}/{max_retries})...[/yellow]"""
            )

        # Create retry tasks for failed chunks
        retry_tasks = []
        chunk_tasks = {}  # Map chunk index to task id

        for chunk_idx in remaining_chunks:
            start, end = chunks[chunk_idx]
            chunk_file = f"{output_file}.part{chunk_idx}"

            task_id = None
            if progress:
                task_id = progress.add_task(
                    f"[cyan]Retry Chunk {chunk_idx +
                                         1} (Attempt {retry_attempt})",
                    total=end - start + 1
                )
            chunk_tasks[chunk_idx] = task_id

            retry_tasks.append(
                download_chunk(session, url, start, end,
                               chunk_file, progress, task_id)
            )

        # Execute retry downloads concurrently
        retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)

        # Update remaining chunks based on retry results
        still_failed = []
        for idx, result in zip(remaining_chunks, retry_results):
            if isinstance(result, Exception) or not result:
                still_failed.append(idx)
                if progress:
                    progress.console.print(
                        f"[red]Chunk {
                            idx + 1} failed on retry attempt {retry_attempt}[/red]"
                    )
            else:
                if progress:
                    progress.console.print(
                        f"[green]Successfully downloaded chunk {
                            idx + 1} on retry[/green]"
                    )

        remaining_chunks = still_failed

        # Add exponential backoff between retries
        if remaining_chunks and retry_attempt < max_retries:
            wait_time = min(2 ** retry_attempt, 60)  # Cap at 60 seconds
            if progress:
                progress.console.print(
                    f"[yellow]Waiting {
                        wait_time}s before next retry...[/yellow]"
                )
            await asyncio.sleep(wait_time)

    return remaining_chunks


async def download_with_fallback(session, url, output_file, progress=None):
    """Fallback to single chunk download when chunked download fails"""
    if progress:
        progress.console.print(
            "[yellow]Falling back to single chunk download...[/yellow]")
    try:
        await download_single_chunk(session, url, output_file, progress)
        return True
    except Exception as e:
        if progress:
            progress.console.print(
                f"[red]Fallback download failed: {str(e)}[/red]")
        return False

async def download_single_chunk(session, url, output_file, progress=None):
    async with session.get(url) as response:
        total_size = int(response.headers.get('Content-Length', 0))
        task_id = None
        if progress:
            task_id = progress.add_task(
                "[cyan]Downloading",
                total=total_size
            )

        with open(output_file, "wb") as f:
            total = 0
            start_time = time.time()
            async for data in response.content.iter_chunked(CHUNK_READ_SIZE):
                f.write(data)
                total += len(data)
                if progress and task_id:
                    elapsed_time = max(time.time() - start_time, 0.001)
                    progress.update(
                        task_id,
                        advance=len(data),
                        speed=total / elapsed_time,
                        description=f"[cyan]Downloaded: {
                            humanize.naturalsize(total)}"
                    )


async def download_chunk(session, url, start, end, chunk_file, progress=None, task_id=None, retries=MAX_RETRIES):
    headers = {
        "Range": f"bytes={start}-{end}",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive"
    }

    for attempt in range(retries):
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 503:
                    wait_time = min(2 ** attempt, MAX_WAIT_TIME)
                    if progress:
                        progress.console.print(
                            f"[yellow]Service unavailable, retrying in {
                                wait_time}s (attempt {attempt + 1}/{retries})[/yellow]"
                        )
                    await asyncio.sleep(wait_time)
                    continue

                if response.status not in (200, 206):
                    if attempt == retries - 1:
                        return False
                    continue

                total = 0
                start_time = time.time()
                with open(chunk_file, "wb") as f:
                    async for data in response.content.iter_chunked(CHUNK_READ_SIZE):
                        f.write(data)
                        total += len(data)
                        if progress and task_id:
                            elapsed_time = max(time.time() - start_time, 0.001)
                            speed = total / elapsed_time
                            progress.update(
                                task_id,
                                advance=len(data),
                                speed=speed,
                                description=f"[cyan]Downloaded: {
                                    humanize.naturalsize(total)}"
                            )
                return True

        except Exception as e:
            if attempt == retries - 1:
                if progress:
                    progress.console.print(
                        f"[red]Error downloading chunk: {str(e)}[/red]")
                return False
            wait_time = min(2 ** attempt, MAX_WAIT_TIME)
            await asyncio.sleep(wait_time)

    return False


async def download_file(url, output_file, progress=None):
    connector = TCPConnector(
        limit=MAX_CONNECTIONS,
        ttl_dns_cache=300,
        enable_cleanup_closed=True,
        force_close=False,
        ssl=False
    )

    timeout = ClientTimeout(total=3600, connect=60)
    session_kwargs = {
        "connector": connector,
        "timeout": timeout,
        "headers": {"Accept-Encoding": "gzip, deflate"}
    }

    async with aiohttp.ClientSession(**session_kwargs) as session:
        try:
            async with session.head(url) as response:
                file_size = int(response.headers.get("Content-Length", 0))
                accept_ranges = response.headers.get("Accept-Ranges", "none")

                if not file_size or accept_ranges.lower() == "none":
                    return await download_with_fallback(session, url, output_file, progress)

            chunk_count = min(MAX_CHUNKS, max(
                4, math.ceil(file_size / (10 * 1024 * 1024))))
            chunk_size = math.ceil(file_size / chunk_count)
            chunks = [(i * chunk_size, min((i + 1) * chunk_size - 1, file_size - 1))
                      for i in range(chunk_count)]

            # Process chunks in batches
            batch_size = min(BATCH_SIZE, chunk_count)
            all_chunk_files = []
            for batch_start in range(0, chunk_count, batch_size):
                batch_end = min(batch_start + batch_size, chunk_count)
                batch_chunks = chunks[batch_start:batch_end]

                download_tasks = []
                chunk_files = []

                for i, (start, end) in enumerate(batch_chunks, start=batch_start):
                    chunk_file = f"{output_file}.part{i}"
                    chunk_files.append(chunk_file)
                    all_chunk_files.append(chunk_file)

                    task_id = None
                    if progress:
                        task_id = progress.add_task(
                            f"[cyan]Chunk {i + 1}/{chunk_count}",
                            total=end - start + 1
                        )

                    download_tasks.append(
                        download_chunk(session, url, start, end,
                                       chunk_file, progress, task_id)
                    )

                # Execute batch downloads concurrently
                results = await asyncio.gather(*download_tasks, return_exceptions=True)

                # Identify failed chunks
                failed_chunks = [
                    i for i, result in enumerate(results, start=batch_start)
                    if isinstance(result, Exception) or not result
                ]

                if failed_chunks:
                    # Retry failed chunks
                    remaining_failed = await retry_failed_chunks(
                        session, url, output_file, chunks, failed_chunks, progress
                    )

                    if remaining_failed:
                        if progress:
                            progress.console.print(
                                f"[red]Failed to download {
                                    len(remaining_failed)} chunks after all retries[/red]"
                            )
                        return await download_with_fallback(session, url, output_file, progress)

            # Combine all successful chunks
            with open(output_file, "wb") as output:
                for chunk_file in all_chunk_files:
                    if os.path.exists(chunk_file):
                        with open(chunk_file, "rb") as part:
                            while data := part.read(BUFFER_SIZE):
                                output.write(data)
                        os.remove(chunk_file)

            if progress:
                progress.console.print(
                    f"[bold green]Download completed: {output_file}[/bold green]")
            return True

        except Exception as e:
            if progress:
                progress.console.print(f"[red]Download failed: {str(e)}[/red]")
            return await download_with_fallback(session, url, output_file, progress)

# Example usage
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Download a file in chunks with progress display.")
    parser.add_argument("url", help="The URL of the file to download")
    parser.add_argument("output_file", help="The output file name")

    args = parser.parse_args()

    asyncio.run(download_file(args.url, args.output_file))
