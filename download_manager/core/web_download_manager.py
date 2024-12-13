import asyncio
import time
from download_manager.core.core_downloader import CoreDownloader
from download_manager.core.download_manager_base import DownloadManagerBase


class WebDownloadManager(DownloadManagerBase):
    def __init__(self, max_concurrent_downloads=4):
        self.max_concurrent_downloads = max_concurrent_downloads
        self.queue = asyncio.Queue()
        self.active_downloads = {}
        self.update_callback = None
        self.tasks = []
        self.running = True

    async def run(self):
        """Implementation of abstract run method"""
        print("Download manager running...")
        self.tasks = []
        for _ in range(self.max_concurrent_downloads):
            task = asyncio.create_task(self.worker())
            self.tasks.append(task)

        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.running = False

        # Cleanup tasks
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()

    async def start(self):
        """Start the download manager"""
        print("Starting download manager...")
        self.running = True
        await self.run()

    def generate_download_id(self, output_file):
        """Generate unique download ID"""
        timestamp = int(time.time() * 1000)
        return f"{output_file}_{timestamp}"

    async def add_download(self, url: str, output_file: str, output_dir: str):
        """Add new download to queue"""
        download_id = self.generate_download_id(output_file)
        self.active_downloads[download_id] = {
            'url': url,
            'output_file': output_file,
            'output_dir': output_dir,
            'status': 'queued',
            'progress': 0
        }
        if self.update_callback:
            await self.update_callback(download_id, 'queued', 0)
        await self.queue.put((download_id, url, output_file, output_dir))
        return download_id

    async def worker(self):
        """Worker process to handle downloads"""
        print("Worker started")
        while self.running:
            try:
                download_id, url, output_file, output_dir = await self.queue.get()
                print(f"Processing download: {output_file} ({download_id})")

                downloader = CoreDownloader(url, output_file, output_dir)

                # Progress wrapper that includes download_id
                async def progress_wrapper(download_id=download_id, status='downloading', progress=0, error=None):
                    await self.update_progress(download_id, status, progress, error)

                # Pass both callback and download_id to EDM
                await downloader.download(
                    update_callback=progress_wrapper,
                    download_id=download_id
                )
                print(f"Download completed: {output_file}")
                self.queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error downloading {output_file}: {e}")
                await self.update_progress(download_id, 'failed', 0, error=str(e))
                self.queue.task_done()

    async def stop(self):
        """Stop download manager and cleanup"""
        self.running = False
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()

    def set_update_callback(self, callback):
        """Set callback for progress updates"""
        self.update_callback = callback

    async def update_progress(self, download_id, status, progress, error=None):
        """Update download progress"""
        if download_id in self.active_downloads:
            self.active_downloads[download_id]['status'] = status
            self.active_downloads[download_id]['progress'] = progress
            if error:
                self.active_downloads[download_id]['error'] = error

        if self.update_callback:
            await self.update_callback(download_id, status, progress, error)

    def get_all_downloads(self):
        """Get current state of all downloads"""
        return self.active_downloads
