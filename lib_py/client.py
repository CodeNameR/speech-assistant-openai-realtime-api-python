import asyncio
import json
from typing import Optional, Dict, Any, Callable, List, Union
from .event_handler import RealtimeEventHandler
from .api import RealtimeAPI
from .conversation import RealtimeConversation
from .utils import RealtimeUtils


# Type Definitions
AudioFormatType = Union["pcm16", "g711_ulaw", "g711_alaw"]

AudioTranscriptionType = Dict[str, Any]  # {"model": "whisper-1"}

TurnDetectionServerVadType = Dict[str, Union[str, float]]

ToolDefinitionType = Dict[str, Any]

SessionResourceType = Dict[str, Any]

ItemStatusType = Union["in_progress", "completed", "incomplete"]

InputTextContentType = Dict[str, Any]  # {"type": "input_text", "text": str}
InputAudioContentType = Dict[str, Any]  # {"type": "input_audio", "audio": Optional[str], "transcript": Optional[str]}
TextContentType = Dict[str, Any]  # {"type": "text", "text": str}
AudioContentType = Dict[str, Any]  # {"type": "audio", "audio": Optional[str], "transcript": Optional[str]}

SystemItemType = Dict[str, Any]
UserItemType = Dict[str, Any]
AssistantItemType = Dict[str, Any]
FunctionCallItemType = Dict[str, Any]
FunctionCallOutputItemType = Dict[str, Any]

FormattedToolType = Dict[str, Any]
FormattedPropertyType = Dict[str, Any]
FormattedItemType = Dict[str, Any]

BaseItemType = Union[SystemItemType, UserItemType, AssistantItemType, FunctionCallItemType, FunctionCallOutputItemType]

ItemType = Dict[str, Any]  # Combination of FormattedItemType and BaseItemType

IncompleteResponseStatusType = Dict[str, Any]
FailedResponseStatusType = Dict[str, Any]
UsageType = Dict[str, int]

ResponseResourceType = Dict[str, Any]


class RealtimeClient(RealtimeEventHandler):
    """
    RealtimeClient Class
    """

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        dangerously_allow_api_key_in_browser: bool = False,
        debug: bool = False,
    ):
        super().__init__()
        self.default_session_config: Dict[str, Any] = {
            "modalities": ["text", "audio"],
            "instructions": "",
            "voice": "alloy",
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": None,
            "turn_detection": None,
            "tools": [],
            "tool_choice": "auto",
            "temperature": 0.8,
            "max_response_output_tokens": 4096,
        }
        self.session_config: Dict[str, Any] = {}
        self.transcription_models: List[Dict[str, str]] = [
            {"model": "whisper-1"},
        ]
        self.default_server_vad_config: Dict[str, Union[str, float, int]] = {
            "type": "server_vad",
            "threshold": 0.5,  # 0.0 to 1.0
            "prefix_padding_ms": 300,  # How much audio to include before speech starts
            "silence_duration_ms": 200,  # How long to wait to mark speech as stopped
        }
        self.realtime = RealtimeAPI(
            url=url,
            api_key=api_key,
            dangerously_allow_api_key_in_browser=dangerously_allow_api_key_in_browser,
            debug=debug,
        )
        self.conversation = RealtimeConversation()
        self.tools: Dict[str, Dict[str, Callable]] = {}
        self.input_audio_buffer: bytes = b""
        self._reset_config()
        self._add_api_event_handlers()

    def _reset_config(self) -> bool:
        """
        Resets sessionConfig and related configurations to default.
        """
        self.session_created: bool = False
        self.tools = {}
        self.session_config = json.loads(json.dumps(self.default_session_config))
        self.input_audio_buffer = b""
        return True

    def _add_api_event_handlers(self):
        """
        Adds API-specific event handlers to manage incoming events from the WebSocket.
        """
        # Example: Handle session updates or other relevant events
        self.realtime.on("server.some_event", self.handle_some_event)
        # Add more event handlers as needed
        return True

    def handle_some_event(self, event: Dict[str, Any]):
        """
        Example event handler. Replace with actual handlers.
        """
        # Implement event handling logic
        pass

    def get_turn_detection_type(self) -> Optional[str]:
        """
        Gets the active turn detection mode.
        """
        return self.session_config.get("turn_detection", {}).get("type", None)

    def add_tool(self, definition: ToolDefinitionType, handler: Callable) -> Dict[str, Callable]:
        """
        Add a tool and its handler.
        """
        if not definition.get("name"):
            raise ValueError("Missing tool name in definition")
        name = definition["name"]
        if name in self.tools:
            raise ValueError(
                f'Tool "{name}" already added. Please use .remove_tool("{name}") before trying to add again.'
            )
        if not callable(handler):
            raise ValueError(f'Tool "{name}" handler must be a function')
        self.tools[name] = {"definition": definition, "handler": handler}
        self.update_session()
        return self.tools[name]

    def remove_tool(self, name: str) -> bool:
        """
        Removes a tool by name.
        """
        if name not in self.tools:
            raise ValueError(f'Tool "{name}" does not exist, cannot be removed.')
        del self.tools[name]
        return True

    def delete_item(self, id: str) -> bool:
        """
        Deletes an item by ID.
        """
        self.realtime.send("conversation.item.delete", {"item_id": id})
        return True

    def update_session(
        self,
        modalities: Optional[List[str]] = None,
        instructions: Optional[str] = None,
        voice: Optional[str] = None,
        input_audio_format: Optional[AudioFormatType] = None,
        output_audio_format: Optional[AudioFormatType] = None,
        input_audio_transcription: Optional[AudioTranscriptionType] = None,
        turn_detection: Optional[TurnDetectionServerVadType] = None,
        tools: Optional[List[ToolDefinitionType]] = None,
        tool_choice: Optional[Union[str, Dict[str, str]]] = None,
        temperature: Optional[float] = None,
        max_response_output_tokens: Optional[Union[int, str]] = None,
    ) -> bool:
        """
        Updates session configuration and sends the update to the server if connected.
        """
        if modalities is not None:
            self.session_config["modalities"] = modalities
        if instructions is not None:
            self.session_config["instructions"] = instructions
        if voice is not None:
            self.session_config["voice"] = voice
        if input_audio_format is not None:
            self.session_config["input_audio_format"] = input_audio_format
        if output_audio_format is not None:
            self.session_config["output_audio_format"] = output_audio_format
        if input_audio_transcription is not None:
            self.session_config["input_audio_transcription"] = input_audio_transcription
        if turn_detection is not None:
            self.session_config["turn_detection"] = turn_detection
        if tools is not None:
            self.session_config["tools"] = tools
        if tool_choice is not None:
            self.session_config["tool_choice"] = tool_choice
        if temperature is not None:
            self.session_config["temperature"] = temperature
        if max_response_output_tokens is not None:
            self.session_config["max_response_output_tokens"] = max_response_output_tokens

        # Load tools from tool definitions + already loaded tools
        use_tools = []
        for tool_def in tools or []:
            definition = {"type": "function", **tool_def}
            if definition["name"] in self.tools:
                raise ValueError(f'Tool "{definition["name"]}" has already been defined')
            use_tools.append(definition)
        for tool in self.tools.values():
            use_tools.append({"type": "function", **tool["definition"]})
        session = self.session_config.copy()
        session["tools"] = use_tools

        if self.realtime.is_connected():
            asyncio.create_task(self.realtime.send("session.update", {"session": session}))
        return True

    def send_user_message_content(self, content: List[Union[InputTextContentType, InputAudioContentType]] = []) -> bool:
        """
        Sends user message content and initiates a response creation.
        """
        if content:
            for c in content:
                if c["type"] == "input_audio":
                    if isinstance(c.get("audio"), (bytes, bytearray)):
                        c["audio"] = RealtimeUtils.array_buffer_to_base64(c["audio"])
            asyncio.create_task(
                self.realtime.send("conversation.item.create", {
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": content,
                    }
                })
            )
        self.create_response()
        return True

    def append_input_audio(self, array_buffer: Union[bytes, bytearray]) -> bool:
        """
        Appends user audio to the existing audio buffer and sends it to the server.
        """
        if len(array_buffer) > 0:
            encoded_audio = RealtimeUtils.array_buffer_to_base64(array_buffer)
            asyncio.create_task(
                self.realtime.send("input_audio_buffer.append", {"audio": encoded_audio})
            )
            self.input_audio_buffer += array_buffer
        return True

    def create_response(self) -> bool:
        """
        Forces a model response generation based on the current input audio buffer.
        """
        if self.get_turn_detection_type() is None and len(self.input_audio_buffer) > 0:
            asyncio.create_task(self.realtime.send("input_audio_buffer.commit"))
            self.conversation.queue_input_audio(self.input_audio_buffer)
            self.input_audio_buffer = b""
        asyncio.create_task(self.realtime.send("response.create"))
        return True

    def cancel_response(self, id: Optional[str] = None, sample_count: int = 0) -> Dict[str, Optional[AssistantItemType]]:
        """
        Cancels the ongoing server generation and truncates ongoing generation, if applicable.
        """
        if not id:
            asyncio.create_task(self.realtime.send("response.cancel"))
            return {"item": None}
        else:
            item = self.conversation.get_item(id)
            if not item:
                raise ValueError(f'Could not find item "{id}"')
            if item.get("type") != "message":
                raise ValueError('Can only cancelResponse messages with type "message"')
            if item.get("role") != "assistant":
                raise ValueError('Can only cancelResponse messages with role "assistant"')

            asyncio.create_task(self.realtime.send("response.cancel"))

            audio_index = next(
                (index for index, c in enumerate(item.get("content", [])) if c.get("type") == "audio"),
                -1,
            )
            if audio_index == -1:
                raise ValueError('Could not find audio on item to cancel')

            audio_end_ms = int((sample_count / self.conversation.default_frequency) * 1000)
            asyncio.create_task(
                self.realtime.send("conversation.item.truncate", {
                    "item_id": id,
                    "content_index": audio_index,
                    "audio_end_ms": audio_end_ms,
                })
            )
            return {"item": item}

    async def wait_for_next_item(self) -> Dict[str, Any]:
        """
        Waits for the next `conversation.item.appended` event and returns the associated item.
        """
        event = await self.wait_for_next("conversation.item.appended")
        item = event.get("item")
        return {"item": item}

    async def wait_for_next_completed_item(self) -> Dict[str, Any]:
        """
        Waits for the next `conversation.item.completed` event and returns the associated item.
        """
        event = await self.wait_for_next("conversation.item.completed")
        item = event.get("item")
        return {"item": item}