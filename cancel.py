async def send_to_twilio():
            """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
            nonlocal stream_sid
            is_streaming = True
            try:
                async for openai_message in openai_ws:
                    response = json.loads(openai_message)
                    if response["type"] in LOG_EVENT_TYPES:
                        print(f"Received event: {response['type']}", response)
                    if response["type"] == "session.updated":
                        print("Session updated successfully:", response)

                    if response["type"] == "input_audio_buffer.speech_started":
                        print("Interruption Occured:", response)
                        openai_ws.send(
                            json.dumps(
                                {"event_id": "testing123", "type": "response.cancel"}
                            )
                        )
                        is_streaming = False

                    if response["type"] == "input_audio_buffer.committed":
                        print("Interruption Completed:", response)
                        # openai_ws.send(
                        #     json.dumps(
                        #         {"event_id": "testing123", "type": "response.cancel"}
                        #     )
                        # )
                        is_streaming = True
                        # await websocket.send_json("response.cancel")

                    if response["type"] == "response.audio.delta" and response.get(
                        "delta"
                    ):
                        if is_streaming:
                            print("AUDIO DELTA HERE INCOMINGGG --------")
                            # Audio from OpenAI
                            try:
                                audio_payload = base64.b64encode(
                                    base64.b64decode(response["delta"])
                                ).decode("utf-8")
                                audio_delta = {
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {"payload": audio_payload},
                                }
                                await websocket.send_json(audio_delta)
                            except Exception as e:
                                print(f"Error processing audio data: {e}")
            except Exception as e:
                print(f"Error in send_to_twilio: {e}")

        await asyncio.gather(receive_from_twilio(), send_to_twilio())