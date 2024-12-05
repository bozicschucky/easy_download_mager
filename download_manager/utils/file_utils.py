import asyncio
import os
import aiofiles
import aiohttp


async def download_single_file(session, url, chunk_read_size, output_file, progress_tracker=None):
    """Download file as a single chunk when splitting fails"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Referer': url
    }

    max_retries = 3
    retry_delay = 2

    # Try to get session cookies first
    cookies = None
    try:
        async with session.get(url, headers=headers) as init_resp:
            if init_resp.status == 200:
                cookies = init_resp.cookies
    except Exception:
        pass  # Continue without cookies if failed

    if progress_tracker:
        progress_tracker.update(total=None)

    request_kwargs = {
        'headers': headers,
        'allow_redirects': True
    }
    if cookies:
        request_kwargs['cookies'] = cookies

    for attempt in range(max_retries):
        try:
            async with session.get(url, **request_kwargs) as response:
                response.raise_for_status()
                total_size = int(response.headers.get('Content-Length', 0))
                if progress_tracker:
                    progress_tracker.update(total=total_size)

                # Ensure output directory exists
                os.makedirs(os.path.dirname(
                    os.path.abspath(output_file)), exist_ok=True)
                downloaded = 0

                async with aiofiles.open(output_file, 'wb') as f:
                    async for data in response.content.iter_chunked(chunk_read_size):
                        await f.write(data)
                        downloaded += len(data)

                        if progress_tracker:
                            progress_tracker.update(downloaded)

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
                if progress_tracker:
                    progress_tracker.log_message(f"Download failed after {
                                                 max_retries} attempts", "error")
                return False

        except Exception as e:
            if progress_tracker:
                progress_tracker.log_message(
                    f"Single file download failed: {str(e)}", "error")
            return False

    return False
