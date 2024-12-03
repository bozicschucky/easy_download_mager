# web_server.py
import os
from aiohttp import web
import logging
from urllib.parse import urlparse, unquote
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
from .edm_cli import sanitize_filename
from .edm import download_file

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()

routes = web.RouteTableDef()


def ensure_downloads_dir():
    """Ensure Downloads directory exists"""
    downloads_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
    os.makedirs(downloads_dir, exist_ok=True)
    return downloads_dir


@routes.post('/download')
async def handle_download(request):
    try:
        data = await request.json()
        url = data.get('url')

        if not url:
            return web.json_response({'error': 'URL required'}, status=400)

        parsed_url = urlparse(url)
        output_file = os.path.basename(parsed_url.path)
        output_file = sanitize_filename(output_file)
        output_dir = ensure_downloads_dir()

        console.print(f"[bold blue]Downloading file to: {
                      output_file}[/bold blue]")

        # Create the progress bar and keep it active during the download
        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
            refresh_per_second=10
        )

        with progress:
            # Await the download directly
            await download_file(
                url=url,
                output_file=output_file,
                output_dir=output_dir,
                progress=progress
            )

        console.print(f"[green]Download completed for {url}[/green]")

        # Return response after the download completes
        return web.json_response({
            'status': 'Download completed',
            'url': url,
            'filename': output_file,
            'output_dir': output_dir
        })

    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        return web.json_response({
            'error': f'Download failed: {str(e)}'
        }, status=500)

app = web.Application()
app.add_routes(routes)

if __name__ == "__main__":
    web.run_app(app, port=5500)
