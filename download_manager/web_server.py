import os
import asyncio
import json
from aiohttp import web
from download_manager.utils.helper_utils import sanitize_filename
from download_manager.core.web_download_manager import WebDownloadManager

routes = web.RouteTableDef()


class DownloadServer:
    def __init__(self):
        self.download_manager = WebDownloadManager(max_concurrent_downloads=4)
        self.active_client = None

    @staticmethod
    def ensure_downloads_dir():
        downloads_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
        os.makedirs(downloads_dir, exist_ok=True)
        return downloads_dir

    async def handle_download(self, request):
        data = await request.json()
        url = data.get('url')
        output_file = data.get('filename')
        if not url:
            return web.json_response({'error': 'URL required'}, status=400)

        output_file = sanitize_filename(output_file or url)
        output_dir = self.ensure_downloads_dir()
        print(f"Adding download: {url} -> {output_file}")
        download_id = await self.download_manager.add_download(url, output_file, output_dir)

        download_info = {
            'type': 'download_added',
            'download_id': download_id,
            'status': 'queued',
            'url': url,
            'filename': output_file,
            'output_dir': output_dir,
            'progress': 0
        }
        await self.broadcast_message(download_info)
        return web.json_response(download_info)

    async def handle_websocket(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.active_client = ws
        print('WebSocket client connected')

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                elif msg.type == web.WSMsgType.ERROR:
                    print(f'WebSocket connection closed with exception {
                          ws.exception()}')
        finally:
            self.active_client = None
            print('WebSocket client disconnected')
        return ws

    async def broadcast_message(self, message):
        if self.active_client is not None:
            try:
                await self.active_client.send_json(message)
            except Exception as e:
                print(f'Failed to send message to client: {e}')
                self.active_client = None

    async def handle_download_update(self, download_id, status, progress=None, error=None):
        update_message = {
            'type': 'download_update',
            'download_id': download_id,
            'status': status,
            'progress': progress,
            'error': error
        }
        await self.broadcast_message(update_message)

    async def start_background_tasks(self, app):
        app['download_manager_task'] = asyncio.create_task(
            self.download_manager.run())
        self.download_manager.set_update_callback(self.handle_download_update)

    async def cleanup_background_tasks(self, app):
        app['download_manager_task'].cancel()
        await app['download_manager_task']


def create_app():
    app = web.Application()
    server = DownloadServer()

    # Routes
    app.router.add_post('/download', server.handle_download)
    app.router.add_get('/ws', server.handle_websocket)

    # Startup/Cleanup
    app.on_startup.append(server.start_background_tasks)
    app.on_cleanup.append(server.cleanup_background_tasks)

    return app


if __name__ == '__main__':
    app = create_app()
    web.run_app(app, host='localhost', port=5500)
