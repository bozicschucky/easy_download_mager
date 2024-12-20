from urllib.parse import urlparse, unquote
import re
import os
import asyncio
import argparse
from utils.download_manager import DownloadManager
from logger.progress_tracker import logger

download_manager = DownloadManager(max_concurrent_downloads=4)


def sanitize_filename(filename: str) -> str:
    """
    Clean filename by:
    1. Decode URL encoding (%20 etc)
    2. Remove invalid characters
    3. Replace spaces properly
    4. Preserve file extension
    """
    # First decode URL encoded characters
    filename = unquote(filename)

    # Split filename and extension
    name, ext = os.path.splitext(filename)
    name = re.sub(r'[<>:"/\\|?*]', '', name)  # Remove Windows invalid chars
    name = re.sub(r'\s+', ' ', name)          # Normalize spaces
    name = name.strip('. ')
    clean_filename = name + ext

    return clean_filename


def main():
    parser = argparse.ArgumentParser(
        description="Download files with progress display."
    )
    parser.add_argument("urls", nargs='+',
                        help="The URLs of the files to download")
    parser.add_argument(
        "-o",
        "--output-dir",
        help="Output directory (default: Downloads folder)",
        default=None
    )
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join(
        os.path.expanduser('~'), 'Downloads')

    async def run_downloads():
        for url in args.urls:
            parsed_url = urlparse(url)
            output_file = os.path.basename(parsed_url.path)
            output_file = sanitize_filename(output_file)
            if not output_file:
                logger.error(
                    f"Could not determine filename from URL: {
                        url}"
                )
                continue
            await download_manager.add_download(url, output_file, output_dir)
        await download_manager.run()

    asyncio.run(run_downloads())



if __name__ == "__main__":
    main()
