import os
import json
import base64
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect, Say, Stream
from dotenv import load_dotenv
import uuid

load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PORT = int(os.getenv('PORT', 3000))
SYSTEM_MESSAGE = (
    "You are a helpful and bubbly AI assistant who loves to chat about "
    "anything the user is interested in and is prepared to offer them facts. "
    "You have a penchant for dad jokes, owl jokes, and rickrolling – subtly. "
    "Always stay positive, but work in a joke when appropriate."
)
VOICE = 'alloy'
LOG_EVENT_TYPES = [
    'response.content.done', 'rate_limits.updated', 'response.done',
    'input_audio_buffer.committed', 'input_audio_buffer.speech_stopped',
    'input_audio_buffer.speech_started', 'session.created'
]

app = FastAPI()

if not OPENAI_API_KEY:
    raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')

@app.get("/", response_class=HTMLResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running!"}

@app.api_route("/incoming", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    response = VoiceResponse()
    # <Say> punctuation to improve text-to-speech flow
    response.say("Please wait while we connect your call to the A. I. voice assistant")
    response.pause(length=1)
    response.say("O.K. you can start talking!")
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

@app.api_route("/status", methods=["GET", "POST"])
async def handle_status(request: Request):
    """Handle status requests from Twilio."""
    return {"status": "ok"}

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections between Twilio and OpenAI."""
    print("Client connected")
    await websocket.accept()

    async with websockets.connect(
        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1"
        }
    ) as openai_ws:
        await send_session_update(openai_ws)
        stream_sid = None
        ai_generating_response = False
        user_speaking = False

        async def receive_from_twilio():
            """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
            nonlocal stream_sid, ai_generating_response, user_speaking
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    event_type = data.get('event')

                    if event_type == 'start':
                        stream_sid = data['start']['streamSid']
                        print(f"Incoming stream has started {stream_sid}")

                    elif event_type == 'media':
                        payload = data['media']['payload']
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": payload
                        }
                        await openai_ws.send(json.dumps(audio_append))

                        if user_speaking and ai_generating_response:
                            print("Interruption detected in Twilio stream. Sending response.cancel.")
                            await send_response_cancel(openai_ws)
                            ai_generating_response = False

                    elif event_type == 'stop':
                        print("Incoming stream has stopped.")
                        if openai_ws.open:
                            await openai_ws.close()

                    elif event_type == 'mark':
                        print(f"Received mark: {data.get('mark', {})}")

                    else:
                        print(f"Received unknown event type: {event_type}")

            except WebSocketDisconnect:
                print("Client disconnected.")
                if openai_ws.open:
                    await openai_ws.close()
            except json.JSONDecodeError:
                print("Received invalid JSON message.")
            except Exception as e:
                print(f"Unexpected error in receive_from_twilio: {e}")

        async def send_to_twilio():
            """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
            nonlocal stream_sid, ai_generating_response, user_speaking
            try:
                async for openai_message in openai_ws:
                    response = json.loads(openai_message)
                    response_type = response.get('type')

                    if response_type in LOG_EVENT_TYPES:
                        print(f"Received event: {response_type}", response)

                    if response_type == 'session.updated':
                        print("Session updated successfully:", response)

                    elif response_type == 'input_audio_buffer.speech_started':
                        user_speaking = True
                        print("User started speaking")
                        if ai_generating_response:
                            print("Interruption detected in OpenAI stream. Sending response.cancel.")
                            await send_response_cancel(openai_ws)
                            ai_generating_response = False

                    elif response_type == 'input_audio_buffer.speech_stopped':
                        user_speaking = False
                        print("User stopped speaking")

                    elif response_type == 'response.audio.delta' and response.get('delta'):
                        if not ai_generating_response:
                            ai_generating_response = True
                            print("AI started generating response")
                        try:
                            audio_payload = base64.b64encode(base64.b64decode(response['delta'])).decode('utf-8')
                            audio_delta = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {
                                    "payload": audio_payload
                                }
                            }
                            await websocket.send_json(audio_delta)
                        except Exception as e:
                            print(f"Error processing audio data: {e}")

                    elif response_type == 'response.done':
                        ai_generating_response = False
                        print("AI finished generating response")

                    # ... [handle other OpenAI events as before] ...

            except json.JSONDecodeError:
                print("Received invalid JSON message from OpenAI.")
            except Exception as e:
                print(f"Error in send_to_twilio: {e}")

        await asyncio.gather(receive_from_twilio(), send_to_twilio())

async def send_session_update(openai_ws):
    """Send session update to OpenAI WebSocket."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.8,
            "input_audio_transcription": {"model": "whisper-1"},

        }
    }
    print('Sending session update:', json.dumps(session_update))
    await openai_ws.send(json.dumps(session_update))


async def send_response_cancel(openai_ws):
    """Send a response.cancel event to OpenAI to handle interruption."""
    cancel_event = {
        "event_id": f"event_{uuid.uuid4()}",
        "type": "response.cancel"
    }
    print('Sending response.cancel event:', json.dumps(cancel_event))
    await openai_ws.send(json.dumps(cancel_event))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)