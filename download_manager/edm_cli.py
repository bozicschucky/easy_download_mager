import os
import asyncio
import argparse
from download_manager.core.cli_download_manager import CLIDownloadManager
from download_manager.utils.helper_utils import extract_filename_from_url
from logger.progress_tracker import logger



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

    download_manager = CLIDownloadManager(max_concurrent_downloads=4)

    async def run_downloads():
        for url in args.urls:
            output_file = extract_filename_from_url(url)
            print(f"Adding download: {url} -> {output_file}")
            if not output_file:
                logger.error(f"Could not determine filename from URL: {url}")
                continue
            await download_manager.add_download(url, output_file, output_dir)
        await download_manager.run()

    asyncio.run(run_downloads())


if __name__ == "__main__":
    main()
