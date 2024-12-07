import asyncio
from logger.progress_tracker import logger
from edm import download_file


class DownloadManager:
    def __init__(self, max_concurrent_downloads: int = 4, progress=None):
        self.semaphore = asyncio.Semaphore(max_concurrent_downloads)
        self.queue = asyncio.Queue()
        self.progress = progress

    async def add_download(self, url: str, output_file: str, output_dir: str):
        await self.queue.put((url, output_file, output_dir))
        logger.info(f"Added download to queue: {output_file}")

    async def worker(self):
        while True:
            try:
                url, output_file, output_dir = await self.queue.get()
                async with self.semaphore:
                    logger.info(f"Starting download: {output_file}")
                    await download_file(
                        url=url,
                        output_file=output_file,
                        output_dir=output_dir,
                        progress=self.progress
                    )
                    logger.info(f"Completed download: {output_file}")
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Exception in worker: {e}")

    async def run(self):
        logger.info("DownloadManager run method started")
        try:
            workers = [asyncio.create_task(self.worker())
                       for _ in range(self.semaphore._value)]
            await asyncio.gather(*workers)
        except asyncio.CancelledError:
            logger.info("DownloadManager run method cancelled")
        except Exception as e:
            logger.error(f"Exception in DownloadManager run method: {e}")
        finally:
            logger.info("DownloadManager run method finished")
