import copy
from typing import Optional, Dict, Any, Tuple
from .utils import RealtimeUtils

ItemContentDeltaType = Dict[str, Any]

class RealtimeConversation:
    def __init__(self):
        self.default_frequency = 24000  # 24,000 Hz
        self.clear()

        self.event_processors = {
            'conversation.item.created': self._process_item_created,
            'conversation.item.truncated': self._process_item_truncated,
            'conversation.item.deleted': self._process_item_deleted,
            'conversation.item.input_audio_transcription.completed': self._process_input_audio_transcription_completed,
            'input_audio_buffer.speech_started': self._process_speech_started,
            'input_audio_buffer.speech_stopped': self._process_speech_stopped,
            'response.created': self._process_response_created,
            'response.output_item.added': self._process_response_output_item_added,
            'response.output_item.done': self._process_response_output_item_done,
            'response.content_part.added': self._process_response_content_part_added,
            'response.audio_transcript.delta': self._process_response_audio_transcript_delta,
            'response.audio.delta': self._process_response_audio_delta,
            'response.text.delta': self._process_response_text_delta,
            'response.function_call_arguments.delta': self._process_response_function_call_arguments_delta,
        }

    def clear(self) -> bool:
        self.item_lookup: Dict[str, Dict[str, Any]] = {}
        self.items: list = []
        self.response_lookup: Dict[str, Dict[str, Any]] = {}
        self.responses: list = []
        self.queued_speech_items: Dict[str, Dict[str, Any]] = {}
        self.queued_transcript_items: Dict[str, Dict[str, Any]] = {}
        self.queued_input_audio: Optional[bytes] = None
        return True

    def queue_input_audio(self, input_audio: bytes) -> bytes:
        self.queued_input_audio = input_audio
        return input_audio

    def process_event(self, event: Dict[str, Any], *args) -> Tuple[Optional[Dict[str, Any]], Optional[ItemContentDeltaType]]:
        if 'event_id' not in event:
            raise ValueError('Missing "event_id" on event')
        if 'type' not in event:
            raise ValueError('Missing "type" on event')

        event_type = event['type']
        processor = self.event_processors.get(event_type)
        if not processor:
            raise ValueError(f'Missing conversation event processor for "{event_type}"')
        
        return processor(event, *args)

    def get_item(self, id: str) -> Optional[Dict[str, Any]]:
        return self.item_lookup.get(id)

    def get_items(self) -> list:
        return self.items.copy()

    # Event Processor Methods
    def _process_item_created(self, event: Dict[str, Any], *args) -> Tuple[Optional[Dict[str, Any]], Optional[ItemContentDeltaType]]:
        item = copy.deepcopy(event.get('item', {}))
        if item['id'] not in self.item_lookup:
            self.item_lookup[item['id']] = item
            self.items.append(item)

        item['formatted'] = {
            'audio': b'',
            'text': '',
            'transcript': ''
        }

        if item['id'] in self.queued_speech_items:
            item['formatted']['audio'] = self.queued_speech_items[item['id']]['audio']
            del self.queued_speech_items[item['id']]

        if 'content' in item:
            text_content = [c for c in item['content'] if c['type'] in ['text', 'input_text']]
            for content in text_content:
                item['formatted']['text'] += content.get('text', '')

        if item['id'] in self.queued_transcript_items:
            item['formatted']['transcript'] = self.queued_transcript_items[item['id']]['transcript']
            del self.queued_transcript_items[item['id']]

        if item['type'] == 'message':
            if item.get('role') == 'user':
                item['status'] = 'completed'
                if self.queued_input_audio:
                    item['formatted']['audio'] = self.queued_input_audio
                    self.queued_input_audio = None
            else:
                item['status'] = 'in_progress'
        elif item['type'] == 'function_call':
            item['formatted']['tool'] = {
                'type': 'function',
                'name': item.get('name', ''),
                'call_id': item.get('call_id', ''),
                'arguments': '',
            }
            item['status'] = 'in_progress'
        elif item['type'] == 'function_call_output':
            item['status'] = 'completed'
            item['formatted']['output'] = item.get('output', '')

        return {'item': item, 'delta': None}

    def _process_item_truncated(self, event: Dict[str, Any], *args) -> Tuple[Optional[Dict[str, Any]], Optional[ItemContentDeltaType]]:
        item_id = event.get('item_id')
        audio_end_ms = event.get('audio_end_ms')
        item = self.item_lookup.get(item_id)
        if not item:
            raise ValueError(f'item.truncated: Item "{item_id}" not found')

        end_index = (audio_end_ms * self.default_frequency) // 1000
        item['formatted']['transcript'] = ''
        item['formatted']['audio'] = item['formatted']['audio'][:end_index]
        return {'item': item, 'delta': None}

    def _process_item_deleted(self, event: Dict[str, Any], *args) -> Tuple[Optional[Dict[str, Any]], Optional[ItemContentDeltaType]]:
        item_id = event.get('item_id')
        item = self.item_lookup.get(item_id)
        if not item:
            raise ValueError(f'item.deleted: Item "{item_id}" not found')

        del self.item_lookup[item_id]
        if item in self.items:
            self.items.remove(item)
        return {'item': item, 'delta': None}

    def _process_input_audio_transcription_completed(self, event: Dict[str, Any], *args) -> Tuple[Optional[Dict[str, Any]], Optional[ItemContentDeltaType]]:
        item_id = event.get('item_id')
        content_index = event.get('content_index')
        transcript = event.get('transcript', ' ')

        item = self.item_lookup.get(item_id)
        if not item:
            self.queued_transcript_items[item_id] = {'transcript': transcript}
            return {'item': None, 'delta': None}
        else:
            if 0 <= content_index < len(item['content']):
                item['content'][content_index]['transcript'] = transcript
                item['formatted']['transcript'] = transcript
            return {'item': item, 'delta': {'transcript': transcript}}

    def _process_speech_started(self, event: Dict[str, Any], *args) -> Tuple[Optional[Dict[str, Any]], Optional[ItemContentDeltaType]]:
        item_id = event.get('item_id')
        audio_start_ms = event.get('audio_start_ms')
        self.queued_speech_items[item_id] = {'audio_start_ms': audio_start_ms}
        return {'item': None, 'delta': None}

    def _process_speech_stopped(self, event: Dict[str, Any], input_audio_buffer: Optional[bytes] = None) -> Tuple[Optional[Dict[str, Any]], Optional[ItemContentDeltaType]]:
        item_id = event.get('item_id')
        audio_end_ms = event.get('audio_end_ms')
        speech = self.queued_speech_items.get(item_id)
        if not speech:
            return {'item': None, 'delta': None}

        speech['audio_end_ms'] = audio_end_ms
        if input_audio_buffer:
            start_index = (speech['audio_start_ms'] * self.default_frequency) // 1000
            end_index = (speech['audio_end_ms'] * self.default_frequency) // 1000
            speech['audio'] = input_audio_buffer[start_index:end_index]

        return {'item': None, 'delta': None}

    def _process_response_created(self, event: Dict[str, Any], *args) -> Tuple[Optional[Dict[str, Any]], Optional[ItemContentDeltaType]]:
        response = event.get('response', {})
        if response.get('id') not in self.response_lookup:
            self.response_lookup[response['id']] = response
            self.responses.append(response)
        return {'item': None, 'delta': None}

    def _process_response_output_item_added(self, event: Dict[str, Any], *args) -> Tuple[Optional[Dict[str, Any]], Optional[ItemContentDeltaType]]:
        response_id = event.get('response_id')
        item = event.get('item')
        response = self.response_lookup.get(response_id)
        if not response:
            raise ValueError(f'response.output_item.added: Response "{response_id}" not found')
        response['output'].append(item['id'])
        return {'item': None, 'delta': None}

    def _process_response_output_item_done(self, event: Dict[str, Any], *args) -> Tuple[Optional[Dict[str, Any]], Optional[ItemContentDeltaType]]:
        item = event.get('item')
        if not item:
            raise ValueError('response.output_item.done: Missing "item"')

        found_item = self.item_lookup.get(item['id'])
        if not found_item:
            raise ValueError(f'response.output_item.done: Item "{item["id"]}" not found')

        found_item['status'] = item.get('status', found_item.get('status', ''))
        return {'item': found_item, 'delta': None}

    def _process_response_content_part_added(self, event: Dict[str, Any], *args) -> Tuple[Optional[Dict[str, Any]], Optional[ItemContentDeltaType]]:
        item_id = event.get('item_id')
        part = event.get('part', {})
        item = self.item_lookup.get(item_id)
        if not item:
            raise ValueError(f'response.content_part.added: Item "{item_id}" not found')
        item['content'].append(part)
        return {'item': item, 'delta': None}

    def _process_response_audio_transcript_delta(self, event: Dict[str, Any], *args) -> Tuple[Optional[Dict[str, Any]], Optional[ItemContentDeltaType]]:
        item_id = event.get('item_id')
        content_index = event.get('content_index')
        delta = event.get('delta', '')

        item = self.item_lookup.get(item_id)
        if not item:
            raise ValueError(f'response.audio_transcript.delta: Item "{item_id}" not found')

        transcript_field = item['content'][content_index].get('transcript', '')
        item['content'][content_index]['transcript'] = transcript_field + delta
        item['formatted']['transcript'] = item['formatted'].get('transcript', '') + delta
        return {'item': item, 'delta': {'transcript': delta}}

    def _process_response_audio_delta(self, event: Dict[str, Any], *args) -> Tuple[Optional[Dict[str, Any]], Optional[ItemContentDeltaType]]:
        item_id = event.get('item_id')
        content_index = event.get('content_index')
        delta = event.get('delta', '')

        item = self.item_lookup.get(item_id)
        if not item:
            raise ValueError(f'response.audio.delta: Item "{item_id}" not found')

        array_buffer = RealtimeUtils.base64_to_array_buffer(delta)
        append_values = array_buffer  # Assuming bytes for audio
        item['formatted']['audio'] = RealtimeUtils.merge_int16_arrays(item['formatted']['audio'], append_values)
        return {'item': item, 'delta': {'audio': append_values}}

    def _process_response_text_delta(self, event: Dict[str, Any], *args) -> Tuple[Optional[Dict[str, Any]], Optional[ItemContentDeltaType]]:
        item_id = event.get('item_id')
        content_index = event.get('content_index')
        delta = event.get('delta', '')

        item = self.item_lookup.get(item_id)
        if not item:
            raise ValueError(f'response.text.delta: Item "{item_id}" not found')

        item['content'][content_index]['text'] += delta
        item['formatted']['text'] = item['formatted'].get('text', '') + delta
        return {'item': item, 'delta': {'text': delta}}

    def _process_response_function_call_arguments_delta(self, event: Dict[str, Any], *args) -> Tuple[Optional[Dict[str, Any]], Optional[ItemContentDeltaType]]:
        item_id = event.get('item_id')
        delta = event.get('delta', '')

        item = self.item_lookup.get(item_id)
        if not item:
            raise ValueError(f'response.function_call_arguments.delta: Item "{item_id}" not found')

        item['arguments'] += delta
        item['formatted']['tool']['arguments'] += delta
        return {'item': item, 'delta': {'arguments': delta}}