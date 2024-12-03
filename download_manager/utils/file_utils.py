import aiofiles


async def download_single_file(session, url, chunk_read_size, output_file, progress=None):
    """Download file as a single chunk when splitting fails"""
    task_id = None
    if progress:
        task_id = progress.add_task(
            "[cyan]Downloading complete file", total=None)

    try:
        async with session.get(url) as response:
            total_size = int(response.headers.get('Content-Length', 0))
            if task_id:
                progress.update(task_id, total=total_size)

            async with aiofiles.open(output_file, 'wb') as f:
                async for data in response.content.iter_chunked(chunk_read_size):
                    await f.write(data)
                    if progress and task_id:
                        progress.update(task_id, advance=len(data))
        return True
    except Exception as e:
        if progress:
            progress.console.print(
                f"[red]Single file download failed: {str(e)}[/red]")
        return False
