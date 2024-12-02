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
        limit_per_host=MAX_CONNECTIONS,
        ttl_dns_cache=300,
        enable_cleanup_closed=True,
        ssl=False
    )
    timeout = ClientTimeout(total=None, connect=60)
    session_kwargs = {
        "connector": connector,
        "timeout": timeout,
        "headers": {"Accept-Encoding": "gzip, deflate"}
    }

    async with aiohttp.ClientSession(**session_kwargs) as session:
        try:
            # Get file size and check if server supports range requests
            async with session.head(url) as response:
                file_size = int(response.headers.get("Content-Length", 0))
                accept_ranges = response.headers.get("Accept-Ranges", "none")
                if not file_size or accept_ranges.lower() == "none":
                    # Fall back to single chunk download
                    return await download_with_fallback(session, url, output_file, progress)

            # Calculate number of chunks using logarithmic function
            size_in_mb = file_size / (1024 * 1024)
            if size_in_mb <= 0:
                num_chunks = 1
            else:
                num_chunks = max(
                    1, min(MAX_CHUNKS, int(math.log2(size_in_mb)) + 1))

            # Compute chunk size
            chunk_size = file_size // num_chunks
            if file_size % num_chunks != 0:
                chunk_size += 1  # Adjust chunk_size to cover the remainder

            # Adjust num_chunks based on the final chunk_size
            num_chunks = (file_size + chunk_size - 1) // chunk_size

            # Generate chunk ranges
            chunks = []
            for i in range(int(num_chunks)):
                start = i * chunk_size
                end = min(start + chunk_size - 1, file_size - 1)
                chunks.append((start, end))

            # Calculate batch size based on number of chunks
            batch_size = max(1, int(math.log2(num_chunks)) + 1)

            all_chunk_files = []
            for batch_start in range(0, num_chunks, batch_size):
                batch_end = min(batch_start + batch_size, num_chunks)
                batch_chunks = chunks[batch_start:batch_end]

                download_tasks = []
                chunk_files = []

                for idx, (start, end) in enumerate(batch_chunks, start=batch_start):
                    chunk_file = f"{output_file}.part{idx}"
                    chunk_files.append(chunk_file)
                    all_chunk_files.append(chunk_file)

                    task_id = None
                    if progress:
                        task_id = progress.add_task(
                            f"[cyan]Chunk {idx + 1}/{num_chunks}",
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
                    idx for idx, result in enumerate(results, start=batch_start)
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
                                    len(remaining_failed)} chunks after retries[/red]"
                            )
                        return await download_with_fallback(session, url, output_file, progress)

            # Combine all successful chunks
            with open(output_file, "wb") as output:
                for i in range(num_chunks):
                    chunk_file = f"{output_file}.part{i}"
                    if os.path.exists(chunk_file):
                        with open(chunk_file, "rb") as part:
                            while True:
                                data = part.read(BUFFER_SIZE)
                                if not data:
                                    break
                                output.write(data)
                        os.remove(chunk_file)

            if progress:
                progress.console.print(f"""[bold green]Download completed: {
                                       output_file}[/bold green]""")
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
