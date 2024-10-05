import asyncio
import json
from typing import Optional
import websockets
from .event_handler import RealtimeEventHandler
from .utils import RealtimeUtils

class RealtimeAPI(RealtimeEventHandler):
    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        dangerously_allow_api_key_in_browser: bool = False,
        debug: bool = False
    ):
        super().__init__()
        self.default_url = 'wss://api.openai.com/v1/realtime'
        self.url = url or self.default_url
        self.api_key = api_key
        self.debug = debug
        self.ws: Optional[websockets.WebSocketClientProtocol] = None

    def is_connected(self) -> bool:
        return self.ws is not None and self.ws.open

    def log(self, *args):
        if self.debug:
            print(f"[WebSocket] {' '.join(map(str, args))}")

    async def connect(self, model: str = 'gpt-4o-realtime-preview-2024-10-01') -> bool:
        if not self.api_key and self.url == self.default_url:
            print(f'Warning: No apiKey provided for connection to "{self.url}"')

        if self.is_connected():
            raise ConnectionError("Already connected")

        headers = {}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
            headers['OpenAI-Beta'] = 'realtime=v1'

        try:
            self.ws = await websockets.connect(f"{self.url}?model={model}", extra_headers=headers)
            self.log(f'Connected to "{self.url}"')

            asyncio.create_task(self._listen())

            return True
        except Exception as e:
            self.log(f'Could not connect to "{self.url}": {e}')
            self.ws = None
            raise ConnectionError(f'Could not connect to "{self.url}"') from e

    async def _listen(self):
        try:
            async for message in self.ws:
                event = json.loads(message)
                await self._handle_message(event)
        except websockets.exceptions.ConnectionClosed as e:
            self.log(f'Disconnected from "{self.url}": {e}')
            await self.dispatch('close', {'error': True})
            self.ws = None

    async def _handle_message(self, event: dict):
        event_type = event.get('type')
        if event_type:
            await self.receive(event_type, event)

    async def send(self, event_name: str, data: Optional[dict] = None) -> bool:
        if not self.is_connected():
            raise ConnectionError("RealtimeAPI is not connected")

        data = data or {}
        if not isinstance(data, dict):
            raise ValueError("data must be a dictionary")

        event = {
            "event_id": RealtimeUtils.generate_id("evt_"),
            "type": event_name,
            **data
        }

        await self.ws.send(json.dumps(event))
        self.dispatch(f"client.{event_name}", event)
        self.log(f"sent: {event_name} {event}")
        return True

    async def disconnect(self):
        if self.ws:
            await self.ws.close()
            self.ws = None
            self.log(f'Disconnected from "{self.url}"')
            await self.dispatch('close', {'error': False})
            return True
        return False