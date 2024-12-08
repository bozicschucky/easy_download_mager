import os
import asyncio
import json
from aiohttp import web, WSCloseCode
from edm_cli import sanitize_filename
from utils.download_manager import DownloadManager as DM

download_manager = DM(max_concurrent_downloads=4, progress=None)
routes = web.RouteTableDef()

# Store WebSocket connection
active_client = None


def ensure_downloads_dir():
    """Ensure Downloads directory exists"""
    downloads_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
    os.makedirs(downloads_dir, exist_ok=True)
    return downloads_dir


@routes.post('/download')
async def handle_download(request):
    data = await request.json()
    url = data.get('url')
    output_file = data.get('filename')
    if not url:
        return web.json_response({'error': 'URL required'}, status=400)

    if output_file:
        output_file = sanitize_filename(output_file)

    output_dir = ensure_downloads_dir()

    # Add download to manager
    download_id = await download_manager.add_download(url, output_file, output_dir)

    download_info = {
        'type': 'download_added',
        'download_id': download_id,
        'status': 'queued',
        'url': url,
        'filename': output_file,
        'output_dir': output_dir,
        'progress': 0
    }
    await broadcast_message(download_info)

    return web.json_response(download_info)


@routes.get('/ws')
async def websocket_handler(request):
    global active_client  # Ensure global declaration is at the start

    if active_client is not None:
        return web.Response(status=409, text="Client already connected")

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    active_client = ws
    print('WebSocket client connected')

    try:
        downloads = download_manager.get_all_downloads()
        await ws.send_json({
            'type': 'current_downloads',
            'downloads': downloads
        })

        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                data = json.loads(msg.data)
                # Handle client messages if needed
                pass
            elif msg.type == web.WSMsgType.ERROR:
                print(f'WebSocket connection closed with exception {
                      ws.exception()}')
    finally:
        active_client = None
        print('WebSocket client disconnected')

    return ws


async def broadcast_message(message):
    global active_client  # Ensure global declaration is at the start

    if active_client is not None:
        try:
            print(f'Sending message to client: {message}')
            await active_client.send_json(message)
        except Exception as e:
            print(f'Failed to send message to client: {e}')
            active_client = None


async def handle_download_update(download_id, status, progress=None, error=None):
    """Handle download status updates"""
    update_message = {
        'type': 'download_update',
        'download_id': download_id,
        'status': status,
        'progress': progress,
        'error': error
    }
    await broadcast_message(update_message)


async def start_background_tasks(app):
    app['download_manager_task'] = asyncio.create_task(download_manager.run())
    download_manager.set_update_callback(handle_download_update)


async def cleanup_background_tasks(app):
    app['download_manager_task'].cancel()
    await app['download_manager_task']

app = web.Application()
app.add_routes(routes)
app.on_startup.append(start_background_tasks)
app.on_cleanup.append(cleanup_background_tasks)

if __name__ == '__main__':
    web.run_app(app, host='localhost', port=5500)
