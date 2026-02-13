"""
Journal Stream – Real-Time Speech-to-Text WebSocket
====================================================

Streams audio from the client to Deepgram and returns live
transcription results over the same WebSocket connection.

Protocol
--------
Connection URL:
    ws://<host>/api/v1/journal/stream?token=<jwt>
    ws://<host>/api/v1/journal/stream?token=<jwt>&sessionId=<id>  (resume)

Client → Server:
    - Binary frames: raw PCM audio (16-bit, 16 kHz, mono)
    - Text frames:   JSON ``{"audio": "<base64>"}``  (from react-native-live-audio-stream)
                     OR raw base64 string
    - Text frame:    JSON ``{"type": "stop"}``  to end the session

Server → Client (JSON text frames):
    - ``{"type": "ready", "sessionId": "..."}``  – ready; client stores sessionId
    - ``{"type": "transcript", ...}``            – partial or final transcript
    - ``{"type": "utterance_end"}``              – speaker stopped talking
    - ``{"type": "speech_started"}``             – speech detected after silence
    - ``{"type": "error", "message": "..."}``    – something went wrong
    - ``{"type": "closed"}``                     – server is done, safe to close
"""

import asyncio
import base64
import json
import logging
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from deepgram.core.events import EventType
from deepgram.extensions.types.sockets import (
    ListenV1ControlMessage,
    ListenV1ResultsEvent,
    ListenV1SpeechStartedEvent,
    ListenV1UtteranceEndEvent,
)

from app.services.audio_session_store import (
    create_session,
    get_session,
    start_cleanup_task,
)
from app.services.deepgram_service import get_deepgram_client

logger = logging.getLogger(__name__)

router = APIRouter()

# Ensure the background cleanup task is running.
start_cleanup_task()


@router.websocket("/stream")
async def realtime_stt(
    websocket: WebSocket,
    sessionId: str | None = Query(default=None),
):
    """
    WebSocket endpoint for real-time speech-to-text transcription.

    Accepts audio from the client, relays it to Deepgram, and forwards
    transcription results back to the client in real time.

    Query params
    ------------
    sessionId : str, optional
        When reconnecting after a pause, pass the ``sessionId`` returned in
        the original ``ready`` message.  Audio chunks will be appended to
        the same session buffer so the save endpoint receives the complete
        recording.
    """
    await websocket.accept()

    # ------------------------------------------------------------------
    # Resolve or create audio session
    # ------------------------------------------------------------------
    if sessionId and get_session(sessionId):
        # Resume — append to existing buffer
        audio_session = get_session(sessionId)
        logger.info("Resuming audio session %s", sessionId)
    else:
        # New session
        session_id = sessionId or str(uuid.uuid4())
        audio_session = create_session(session_id)
        logger.info("Created new audio session %s", session_id)

    client = get_deepgram_client()
    listen_task = None

    try:
        async with client.listen.v1.connect(
            model="nova-2",
            language="en",
            encoding="linear16",
            sample_rate="16000",
            channels="1",
            smart_format="true",
            punctuate="true",
            interim_results="true",
            utterance_end_ms="1000",
            vad_events="true",
        ) as dg_connection:

            # ---------------------------------------------------------
            # Deepgram event callbacks – forward events to the client
            # ---------------------------------------------------------

            async def on_message(event):
                """Route Deepgram events to the client WebSocket."""
                try:
                    if isinstance(event, ListenV1ResultsEvent):
                        transcript = event.channel.alternatives[0].transcript
                        if not transcript:
                            return
                        await websocket.send_json({
                            "type": "transcript",
                            "text": transcript,
                            "is_final": event.is_final,
                            "speech_final": event.speech_final,
                            "confidence": event.channel.alternatives[0].confidence,
                        })

                    elif isinstance(event, ListenV1UtteranceEndEvent):
                        await websocket.send_json({"type": "utterance_end"})

                    elif isinstance(event, ListenV1SpeechStartedEvent):
                        await websocket.send_json({"type": "speech_started"})

                except Exception as e:
                    logger.error("Error forwarding Deepgram event to client: %s", e)

            async def on_error(error):
                """Forward Deepgram errors to the client."""
                logger.error("Deepgram error: %s", error)
                try:
                    await websocket.send_json({
                        "type": "error",
                        "message": str(error),
                    })
                except Exception:
                    pass

            dg_connection.on(EventType.MESSAGE, on_message)
            dg_connection.on(EventType.ERROR, on_error)

            # Start receiving Deepgram events in a background task
            listen_task = asyncio.create_task(dg_connection.start_listening())

            # Tell the client we're ready — include the sessionId
            await websocket.send_json({
                "type": "ready",
                "sessionId": audio_session.session_id,
            })

            # ---------------------------------------------------------
            # Main loop – read from client, relay audio to Deepgram
            # and accumulate chunks in the session buffer.
            # ---------------------------------------------------------

            while True:
                message = await websocket.receive()

                # Client disconnected at the transport level
                if message.get("type") == "websocket.disconnect":
                    break

                # --- Binary frame: raw PCM audio ---
                if "bytes" in message:
                    raw = message["bytes"]
                    audio_session.append(raw)
                    await dg_connection.send_media(raw)
                    continue

                # --- Text frame: JSON control message or base64 audio ---
                if "text" in message:
                    text = message["text"]

                    # Try to parse as JSON first
                    try:
                        data = json.loads(text)

                        # Stop command
                        if data.get("type") == "stop":
                            break

                        # JSON-wrapped base64 audio: {"audio": "..."}
                        if "audio" in data:
                            audio_bytes = base64.b64decode(data["audio"])
                            audio_session.append(audio_bytes)
                            await dg_connection.send_media(audio_bytes)
                            continue

                    except (json.JSONDecodeError, ValueError):
                        pass

                    # Fallback: treat the entire text frame as raw base64
                    try:
                        audio_bytes = base64.b64decode(text)
                        audio_session.append(audio_bytes)
                        await dg_connection.send_media(audio_bytes)
                    except Exception:
                        logger.warning("Received unrecognized text message on WS")

            # Signal Deepgram to finalize and close
            try:
                await dg_connection.send_control(
                    ListenV1ControlMessage(type="CloseStream")
                )
            except Exception:
                pass

    except WebSocketDisconnect:
        logger.info("Client disconnected from STT stream (session %s)", audio_session.session_id)

    except Exception as e:
        logger.error("STT WebSocket error: %s", e, exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass

    finally:
        # Cancel the background listener task
        if listen_task and not listen_task.done():
            listen_task.cancel()
            try:
                await listen_task
            except asyncio.CancelledError:
                pass

        # Signal to the client that the session is over
        try:
            await websocket.send_json({"type": "closed"})
        except Exception:
            pass

        try:
            await websocket.close()
        except Exception:
            pass

        logger.info(
            "STT stream session ended (session %s, %d bytes accumulated)",
            audio_session.session_id,
            audio_session.total_bytes,
        )
