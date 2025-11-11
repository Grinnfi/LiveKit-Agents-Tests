import logging
import os
import asyncio
import re # change llm output
import json # dump data
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import List, Union

import wave

from dotenv import load_dotenv
from livekit.agents import (
    NOT_GIVEN,
    Agent,
    AgentFalseInterruptionEvent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    RunContext,
    WorkerOptions,
    cli,
    metrics,
    llm,
    FunctionTool,
    ConversationItemAddedEvent,
)
from livekit.plugins import cartesia, deepgram, noise_cancellation, google
from livekit.plugins import silero #VAD, VADStream, onnx_model
from livekit.agents.vad import VADEvent, VADEventType

from typing import AsyncIterable #play audio as speach
from livekit import rtc # audio lib
from livekit.agents.utils.codecs import AudioStreamDecoder #decode audio for streaming
from pathlib import Path

# from livekit.agents.voice.agent import ModelSettings# log tts
# from livekit.agents.voice.io import TimedString # log tts
# from collections.abc import AsyncGenerator, AsyncIterable
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from agents.common.states import CallState
from agents.welcome.agent import WelcomeAgent

logging.basicConfig(filename='welcome_agent.log', level=logging.INFO)
logger = logging.getLogger("agent")

load_dotenv()

ROOM_FRAME_RATE = 16000

def _write_wav_frames_original(original_file, original_data: bytes):
    """Thread-safe helper to write WAV frames."""
    original_file.writeframes(original_data)

async def _save_forward_audio_task(self) -> None:
    audio_input = self.input.audio
    if audio_input is None:
        return

    original_file = None
    write_executor = None
    if hasattr(self, "log_dir") and self.log_dir:
        original_file = wave.open(f"{self.log_dir}/original.wav", "wb")
        original_file.setnchannels(1)  # mono
        original_file.setsampwidth(2)  # 16-bit
        original_file.setframerate(ROOM_FRAME_RATE)
        # filtered_file = wave.open(f"{self.log_dir}/filtered.wav", "wb")
        # filtered_file.setnchannels(1)  # mono
        # filtered_file.setsampwidth(2)  # 16-bit
        # filtered_file.setframerate(ROOM_FRAME_RATE)

        write_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="wav_writer"
        )
    loop = asyncio.get_event_loop()
    async for frame in audio_input:
        if self._activity is not None:
            # original_data = frame.data.tobytes()

            # TODO: HPF -> EC -> RNNoise (or another DNN NS) -> AGC / final gain — disable the WebRTC NS when you run RNNoise
            # denoised_frame = self.denoiser.process(frame)
            self._activity.push_audio(frame)

            if original_file:
                loop.run_in_executor(
                    write_executor,
                    _write_wav_frames_original,
                    original_file,
                    frame.data.tobytes(),
                )


# # -- custom vad --
# def push_frame(self, frame: rtc.AudioFrame) -> None:
#     self._check_input_not_ended()
#     self._check_not_closed()
#     # self.original_file.writeframes(frame.data.tobytes())
#     # denoised_frame = self.denoiser.process(frame)
#     # self.filtered_file.writeframes(denoised_frame.data.tobytes())
#     self._input_ch.send_nowait(frame)

# def stream(self) -> VADStream:
#     # denoiser = RNNoiseDenoiser(sample_rate=ROOM_FRAME_RATE)
#     VADStream.push_frame = push_frame
#     stream = VADStream(
#         self,
#         self._opts,
#         onnx_model.OnnxModel(
#             onnx_session=self._onnx_session, sample_rate=self._opts.sample_rate
#         ),
#     )
#     self._streams.add(stream)
#     return stream

# VAD.stream = stream # overwrite stream logic


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

# @dataclass
# class UserData:
#     # https://github.com/livekit/livekit_composite/blob/cd1a2500/livekit-examples/python-agents-examples/context-readmes/USERDATA_GUIDE.md#basic-structure
#     # Required context reference
#     ctx: JobContext
    
#     # Participant information etc
#     test_data: str = ""
    
#     # Application state
#     conversation_history: List[Dict[str, Any]] = field(default_factory=list)
#     state: str = "initial"
#     state_history: List[str] = field(default_factory=list)
    
#     # Business logic data
#     user_preferences: Dict[str, Any] = field(default_factory=dict)
#     session_data: Dict[str, Any] = field(default_factory=dict)

#     def transition_to(self, new_state: str):
#         self.state_history.append(self.state)
#         self.state = new_state

@dataclass
class SessionStateTracker:
    """
    Stores the log of ALL state segments. The last entry is the ACTIVE segment.
    Format: List of [state_name (str), interaction_count (int)]
    """
    # https://github.com/livekit/livekit_composite/blob/cd1a2500/livekit-examples/python-agents-examples/context-readmes/USERDATA_GUIDE.md
    ctx: JobContext # LiveKit context
    state: str # The currently active state
    session_log: List[List[Union[str, int]]] = field(default_factory=list)
    
    def __post_init__(self):
        """Initializes the session log with the starting state and a count of 0."""
        self.session_log.append([self.state, 0])
    
    def transition_to(self, new_agent: str):
        """
        Saves the agent transition on session.session_log
        Add the new agent to the session_log with a interaction count of 0.
        """
        self.state = new_agent
        self.session_log.append([new_agent, 0])

    def count_state_interaction(self):
        """
        Increments the interaction counter for the last entry in the session_log, 
        which always represents the current active state.
        """
        if self.session_log:
            # session_log[-1] refers to the last (active) segment.
            # session_log[-1][1] refers to the integer count within that segment.
            self.session_log[-1][1] += 1
        else:
            # Fallback: If the log is somehow empty, re-initialize the state segment.
            print("Error: session_log is empty. Re-initializing current state.")
            self.session_log.append([self.state, 1])


async def entrypoint(ctx: JobContext):
    client_data = CallState(client_name='Daniel', client_cpf='12344444789', enterprise_name='LiveKit')
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    session_state_tracker = SessionStateTracker(ctx=ctx)
    
    # Set up a voice AI pipeline using Gemini, Cartesia, Deepgram, and the LiveKit turn detector
    session = AgentSession[SessionStateTracker](
        session_state_tracker = session_state_tracker,
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all providers at https://docs.livekit.io/agents/integrations/llm/
        # llm=google.beta.realtime.RealtimeModel(model="gemini-2.0-flash-exp",voice="Puck"),
        llm=google.LLM(model="gemini-2.0-flash"),
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # See all providers at https://docs.livekit.io/agents/integrations/stt/
        stt=deepgram.STT(model="nova-3", language="pt-BR"),
        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
        # See all providers at https://docs.livekit.io/agents/integrations/tts/
        tts=cartesia.TTS(voice="1cf751f6-8749-43ab-98bd-230dd633abdb"),#Ana Paula
        use_tts_aligned_transcript= True, # shows time of each word in transcription
        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
        # See more at https://docs.livekit.io/agents/build/turns
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # allow the LLM to generate a response while waiting for the end of turn
        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
        preemptive_generation=False,
    )

    # To use a realtime model instead of a voice pipeline, use the following session setup instead:
    # session = AgentSession(
    #     # See all providers at https://docs.livekit.io/agents/integrations/realtime/
    #     llm=google.realtime.RealtimeModel(voice="gemini-flash")
    # )

    # sometimes background noise could interrupt the agent session, these are considered false positive interruptions
    # when it's detected, you may resume the agent's speech
    @session.on("agent_false_interruption")
    def _on_agent_false_interruption(ev: AgentFalseInterruptionEvent):
        logger.info("false positive interruption, resuming")
        session.generate_reply(instructions=ev.extra_instructions or NOT_GIVEN)

    # Metrics collection, to measure pipeline performance
    # For more information, see https://docs.livekit.io/agents/build/metrics/
    usage_collector = metrics.UsageCollector()

    now = datetime.now(ZoneInfo("America/Sao_Paulo"))
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S-%f")[:-3]
    log_dir = os.path.join("logs", timestamp)
    os.makedirs(log_dir, exist_ok=True)
    
    AgentSession.log_dir = log_dir
    AgentSession._forward_audio_task = _save_forward_audio_task

    # Event handler to save probability and audio
    # def save_debug_data(ev):
        # speech_dir = os.path.join(log_dir, f"{timestamp}speech_probability.json")
        # audio_dir = os.path.join(log_dir, f"{timestamp}audio_frames.raw")

        # # Save speech probability
        # with open(speech_dir, "a") as prob_file:
        #     json.dump({"timestamp": ev.timestamp, "probability": ev.probability}, prob_file)
        #     prob_file.write("\n")

        # # Save audio frames
        # with open(audio_dir, "ab") as audio_file:
        #     for frame in ev.frames:
        #         audio_file.write(frame.data)

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)
        # print(ev.metrics)
        # if ev.type == "inference_done":
        #     save_debug_data(ev)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    # # Add a virtual avatar to the session, if desired
    # # For other providers, see https://docs.livekit.io/agents/integrations/avatar/
    # avatar = hedra.AvatarSession(
    #   avatar_id="...",  # See https://docs.livekit.io/agents/integrations/avatar/hedra
    # )
    # # Start the avatar and wait for it to join
    # await avatar.start(session, room=ctx.room)

    # Start the session, which initializes the voice pipeline and warms up the models
    await session.start(
        agent=WelcomeAgent(state=client_data),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # LiveKit Cloud enhanced noise cancellation
            # - If self-hosting, omit this parameter
            # - For telephony applications, use `BVCTelephony` for best results
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Join the room and connect to the user
    await ctx.connect()

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
