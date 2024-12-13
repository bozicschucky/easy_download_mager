import asyncio
import time
from logger.progress_tracker import logger
from edm import download_file


class DownloadManager:
    def __init__(self, max_concurrent_downloads: int = 4, progress=None):
        self.semaphore = asyncio.Semaphore(max_concurrent_downloads)
        self.queue = asyncio.Queue()
        self.progress = progress
        self.update_callback = None  # Added callback attribute
        self.active_downloads = {}   # Added active downloads tracking

    def set_update_callback(self, callback):
        """Set the callback function to be called on updates."""
        self.update_callback = callback

    async def add_download(self, url: str, output_file: str, output_dir: str):
        await self.queue.put((url, output_file, output_dir))
        logger.info(f"Added download to queue: {output_file}")
        # Notify about download queued
        if self.update_callback:
            await self.update_callback(
                download_id=None,
                status='queued',
                progress=0,
                error=None
            )

    async def worker(self):
        while True:
            try:
                url, output_file, output_dir = await self.queue.get()
                async with self.semaphore:
                    logger.info(f"Starting download: {output_file}")
                    download_id = f"{output_file}_{int(time.time())}"
                    # Track active download
                    self.active_downloads[download_id] = {
                        'id': download_id,
                        'url': url,
                        'filename': output_file,
                        'status': 'downloading',
                        'progress': 0
                    }
                    # Notify about download started
                    if self.update_callback:
                        await self.update_callback(
                            download_id=download_id,
                            status='started',
                            progress=0,
                            error=None
                        )
                    # Perform the download with progress updates
                    await download_file(
                        url=url,
                        output_file=output_file,
                        output_dir=output_dir,
                        progress=self.progress,
                        update_callback=self.update_callback,
                        download_id=download_id
                    )
                    logger.info(f"Completed download: {output_file}")
                    # Update status
                    self.active_downloads[download_id]['status'] = 'completed'
                    self.active_downloads[download_id]['progress'] = 100
                    if self.update_callback:
                        await self.update_callback(
                            download_id=download_id,
                            status='completed',
                            progress=100,
                            error=None
                        )
                    # Remove from active downloads
                    del self.active_downloads[download_id]
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Exception in worker: {e}")
                if self.update_callback:
                    await self.update_callback(
                        download_id=download_id,
                        status='failed',
                        progress=None,
                        error=str(e)
                    )
                self.queue.task_done()

    async def run(self):
        logger.info("DownloadManager run method started")
        try:
            workers = [asyncio.create_task(self.worker())
                       for _ in range(self.semaphore._value)]
            while True:
                await asyncio.sleep(3600)  # Keep the loop running
        except asyncio.CancelledError:
            logger.info("DownloadManager run method cancelled")
        except Exception as e:
            logger.error(f"Exception in DownloadManager run method: {e}")
        finally:
            for worker in workers:
                worker.cancel()
                try:
                    await worker
                except asyncio.CancelledError:
                    pass
            logger.info("DownloadManager run method finished")

    def get_all_downloads(self):
        """Return a list of all active downloads."""
        return list(self.active_downloads.values())
