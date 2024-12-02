from rich.console import Console
from rich.progress import Progress, BarColumn, DownloadColumn, TextColumn, TimeRemainingColumn, TransferSpeedColumn
import asyncio
import argparse
from urllib.parse import urlparse, unquote
import os
import re
from utils import download_file

console = Console()


def sanitize_filename(filename):
    # Remove invalid characters and decode URL-encoded characters
    filename = unquote(filename)
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename


def main():
    parser = argparse.ArgumentParser(
        description="Download a file with progress display."
    )
    parser.add_argument("url", help="The URL of the file to download")

    args = parser.parse_args()

    # Generate output file name from URL
    parsed_url = urlparse(args.url)
    output_file = os.path.basename(parsed_url.path)
    output_file = sanitize_filename(output_file)
    if not output_file:
        console.print(
            "[bold red]Error: Unable to determine the output file name from the URL.[/bold red]")
        return

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        asyncio.run(download_file(
            args.url, output_file, progress
        ))


if __name__ == "__main__":
    main()
