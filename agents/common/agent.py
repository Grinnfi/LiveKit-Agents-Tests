import logging
from logging import Logger

import re # change llm output
import os

from typing import AsyncIterable, AsyncGenerator, ClassVar

from livekit.agents import (
    Agent,
    llm,
    FunctionTool,
    function_tool,
    ModelSettings, #log tts
    RunContext,
)

from agents.common.states import CallState
from livekit.agents.voice.io import TimedString # log tts

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class BaseAgent(Agent):
    logging.basicConfig(filename='agent.log', level=logging.INFO)
    logger: Logger

    state: CallState 
    # The ONE reusable variable defining the common context/persona
    instructions_base: ClassVar[str]

    with open(os.path.join(BASE_DIR, "prompt.md"), "r") as file:
        instructions_base = file.read()

    def __init__(self, state: CallState, instructions: str | None = None) -> None:  
        agent_instructions = instructions if instructions is not None else self.instructions_base.format(state=state)

        super().__init__(instructions= agent_instructions)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.state = state 

    async def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list[FunctionTool],
        model_settings: ModelSettings
    ) -> AsyncIterable[llm.ChatChunk]:
        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            # Changes LLM output
            def process_stream(chunk):
                content = getattr(chunk.delta, 'content', None) if hasattr(chunk, 'delta') else None
                if content is None:
                    return chunk
                
                # Exemplo - troca "Oi" por "Olá"
                pattern = re.compile(r"\bOi\b",re.IGNORECASE) #\b = word boundry
                processed_content = re.sub(pattern, "Olá", content)

                chunk.delta.content = processed_content
                return chunk

            yield process_stream(chunk=chunk)

    @function_tool
    async def debug(
        self,
        context: RunContext
    ) -> str:
        """Prints debug information when asked by the user.
        """
        self.logger.info("Printing debug.")
        print(f"""\
            History:
              {self.session.history.to_dict()}
            State:
                {self.state}
            Test - chat ctx:
                {self.chat_ctx.to_dict()}
        """)
        return "Debug Printed"
    
    @function_tool
    async def end_call(self) -> None:  
        """Use this tool to end the call."""  
        # Generate and wait for the reply to complete
        speech_handle = self.session.say("Tchau.")

        # Wait for the speech to actually finish  
        await speech_handle  
        
        # Now safely close the session  
        await self.session.drain()  
        await self.session.aclose()  
        
        return None

    # Prints transcription and timing
    async def transcription_node(
        self, text: AsyncIterable[str | TimedString], model_settings: ModelSettings
    ) -> AsyncGenerator[str | TimedString, None]:
        async for chunk in text:
            if isinstance(chunk, TimedString):
                self.logger.info(f"TimedString: '{chunk}' ({chunk.start_time} - {chunk.end_time})")
            yield chunk

    async def on_enter(self):
        # try:
        #     audio_frames = load_audio_file(audio_file)
        #     await self.session.say(".", audio=audio_frames, allow_interruptions=False)
        #     # await asyncio.sleep(3)
        # except FileNotFoundError as e:
        #     logger.error("Pre-roll audio file not found, continuing without audio: %s", e)
        # except Exception as e:
        #     logger.error("Error loading pre-roll audio file: %s", e)

        # self.session.say("",audio=audio_frames, allow_interruptions=False)
        # self.session.say("Oi.")
        print("READY")
        return await super().on_enter()