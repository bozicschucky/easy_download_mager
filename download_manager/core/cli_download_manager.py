import asyncio
from download_manager.core.core_downloader import CoreDownloader
from download_manager.core.download_manager_base import DownloadManagerBase


class CLIDownloadManager(DownloadManagerBase):
    def __init__(self, max_concurrent_downloads=4):
        self.max_concurrent_downloads = max_concurrent_downloads
        self.queue = asyncio.Queue()
        self.active_downloads = {}
        self.update_callback = None

    async def add_download(self, url, output_file, output_dir):
        await self.queue.put((url, output_file, output_dir))

    async def run(self):
        tasks = []
        for _ in range(self.max_concurrent_downloads):
            task = asyncio.create_task(self.worker())
            tasks.append(task)
        await self.queue.join()
        for task in tasks:
            task.cancel()

    async def worker(self):
        while True:
            try:
                url, output_file, output_dir = await self.queue.get()
                downloader = CoreDownloader(url, output_file, output_dir)
                await downloader.download_cli()
                self.queue.task_done()
            except asyncio.CancelledError:
                break
