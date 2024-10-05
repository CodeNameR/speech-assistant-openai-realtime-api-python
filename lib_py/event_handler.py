import asyncio
from typing import Callable, Dict, List, Any, Optional

async def sleep(t: float):
    await asyncio.sleep(t)

class RealtimeEventHandler:
    def __init__(self):
        self.event_handlers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self.next_event_handlers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}

    def clear_event_handlers(self) -> bool:
        self.event_handlers.clear()
        self.next_event_handlers.clear()
        return True

    def on(self, event_name: str, callback: Callable[[Dict[str, Any]], None]) -> Callable:
        if event_name not in self.event_handlers:
            self.event_handlers[event_name] = []
        self.event_handlers[event_name].append(callback)
        return callback

    def on_next(self, event_name: str, callback: Callable[[Dict[str, Any]], None]) -> Callable:
        if event_name not in self.next_event_handlers:
            self.next_event_handlers[event_name] = []
        self.next_event_handlers[event_name].append(callback)
        return callback

    def off(self, event_name: str, callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> bool:
        handlers = self.event_handlers.get(event_name, [])
        if callback:
            if callback in handlers:
                handlers.remove(callback)
            else:
                raise ValueError(f'Could not turn off specified event listener for "{event_name}": not found as a listener')
        else:
            self.event_handlers.pop(event_name, None)
        return True

    def off_next(self, event_name: str, callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> bool:
        next_handlers = self.next_event_handlers.get(event_name, [])
        if callback:
            if callback in next_handlers:
                next_handlers.remove(callback)
            else:
                raise ValueError(f'Could not turn off specified next event listener for "{event_name}": not found as a listener')
        else:
            self.next_event_handlers.pop(event_name, None)
        return True

    async def wait_for_next(self, event_name: str, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        next_event = None
        event_future = asyncio.get_event_loop().create_future()

        def handler(event):
            nonlocal next_event
            if not event_future.done():
                event_future.set_result(event)

        self.on_next(event_name, handler)

        try:
            next_event = await asyncio.wait_for(event_future, timeout=timeout)
        except asyncio.TimeoutError:
            next_event = None

        return next_event

    def dispatch(self, event_name: str, event: Dict[str, Any]) -> bool:
        handlers = self.event_handlers.get(event_name, []).copy()
        for handler in handlers:
            handler(event)

        next_handlers = self.next_event_handlers.get(event_name, []).copy()
        for next_handler in next_handlers:
            next_handler(event)

        if event_name in self.next_event_handlers:
            del self.next_event_handlers[event_name]

        return True