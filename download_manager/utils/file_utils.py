import asyncio
import os
import time
import aiofiles
import aiohttp


async def download_single_file(session, url, chunk_size, output_file, progress_tracker=None):
    """Download file as a single stream with optimized settings."""
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': '*/*',
    }

    max_retries = 5
    retry_delay = 2
    chunk_size = 1048576  # Use a larger chunk size (1 MB)

    for attempt in range(max_retries):
        try:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                total_size = int(response.headers.get('Content-Length', 0))

                # Ensure output directory exists
                os.makedirs(os.path.dirname(
                    os.path.abspath(output_file)), exist_ok=True)

                downloaded = 0
                start_time = time.time()

                async with aiofiles.open(output_file, 'wb') as f:
                    async for data in response.content.iter_chunked(chunk_size):
                        await f.write(data)
                        downloaded += len(data)

                        # Calculate progress metrics
                        elapsed = max(time.time() - start_time, 0.001)
                        speed = downloaded / elapsed
                        # percentage = (downloaded / total_size) * \
                        #     100 if total_size else 0
                        time_left = (total_size - downloaded) / \
                            speed if speed > 0 else 0

                        if progress_tracker:
                            progress_tracker.update(
                                downloaded=downloaded,
                                total_size=total_size,
                                speed=speed,
                                time_left=time_left
                            )

                # Verify download size
                if total_size > 0 and downloaded != total_size:
                    raise ValueError(f"Download size mismatch: {
                                     downloaded} != {total_size}")

                if progress_tracker:
                    progress_tracker.log_message(
                        f"Download completed: {output_file}", "success")
                return True

        except aiohttp.ClientError as e:
            if progress_tracker:
                progress_tracker.log_message(f"Network error: {str(e)}")
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                if progress_tracker:
                    progress_tracker.log_message(
                        f"Retrying in {wait_time}s... ({attempt + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
            else:
                return False
        except Exception as e:
            if progress_tracker:
                progress_tracker.log_message(
                    f"Download failed: {str(e)}", "error")
            return False

    return False
