import asyncio
import os
from aiohttp import web
import logging
from urllib.parse import urlparse, unquote
from download_manager.edm_cli import sanitize_filename
from download_manager.utils.download_manager import DownloadManager as DM

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

download_manager = DM(max_concurrent_downloads=4, progress=None)

routes = web.RouteTableDef()


def ensure_downloads_dir():
    """Ensure Downloads directory exists"""
    downloads_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
    os.makedirs(downloads_dir, exist_ok=True)
    return downloads_dir


@routes.post('/download')
async def handle_download(request):
    data = await request.json()
    url = data.get('url')
    if not url:
        return web.json_response({'error': 'URL required'}, status=400)

    parsed_url = urlparse(url)
    output_file = os.path.basename(parsed_url.path)
    output_file = sanitize_filename(output_file)
    output_dir = ensure_downloads_dir()

    await download_manager.add_download(url, output_file, output_dir)

    return web.json_response({
        'status': 'Download queued',
        'url': url,
        'filename': output_file,
        'output_dir': output_dir
    })


async def start_background_tasks(app):
    app['download_manager_task'] = asyncio.create_task(download_manager.run())


async def cleanup_background_tasks(app):
    app['download_manager_task'].cancel()
    await app['download_manager_task']

app = web.Application()
app.add_routes(routes)
app.on_startup.append(start_background_tasks)
app.on_cleanup.append(cleanup_background_tasks)

if __name__ == "__main__":
    web.run_app(app, port=5500)
