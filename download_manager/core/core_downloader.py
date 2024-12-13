# core_downloader.py
from edm import EDM


class CoreDownloader:
    def __init__(self, url, output_file, output_dir):
        self.url = url
        self.output_file = output_file
        self.output_dir = output_dir

    async def download(self, update_callback=None, download_id=None):
        print(f"Starting download of {self.output_file}")
        if update_callback:
            await update_callback('downloading', 0)

        try:
            # Pass both callback and download_id to EDM
            await EDM.download_file(
                url=self.url,
                output_file=self.output_file,
                output_dir=self.output_dir,
                update_callback=update_callback,
                download_id=download_id
            )
            if update_callback:
                await update_callback('completed', 100)
        except Exception as e:
            print(f"Download failed: {str(e)}")
            if update_callback:
                await update_callback('failed', 0, str(e))
            raise

    async def download_cli(self):
        await EDM.download_file(
            url=self.url,
            output_file=self.output_file,
            output_dir=self.output_dir
        )
