from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
from urllib.parse import urlparse, unquote
import re
import os
import asyncio
import argparse
from download_manager.edm import download_file

console = Console()


def sanitize_filename(filename):
    """Sanitize a filename by removing invalid characters."""
    filename = unquote(filename)
    return re.sub(r'[\\/*?:"<>|]', "", filename)


def main():
    parser = argparse.ArgumentParser(
        description="Download a file with progress display.")
    parser.add_argument("url", help="The URL of the file to download")
    args = parser.parse_args()

    # Generate output file name from URL
    parsed_url = urlparse(args.url)
    output_file = os.path.basename(parsed_url.path)
    output_file = sanitize_filename(output_file)

    if not output_file:
        console.print(
            "[bold red]Error: Could not determine output file name from URL.[/bold red]")
        return

    console.print(f"[bold blue]Downloading file to: {output_file}[/bold blue]")

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        asyncio.run(download_file(args.url, output_file, progress))


if __name__ == "__main__":
    main()
