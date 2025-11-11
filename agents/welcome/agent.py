import logging
import os

from livekit.agents import (
    Agent,
    function_tool,
)

from agents.common.states import CallState
from agents.common.agent import BaseAgent
from agents.pid.agent import PidAgent

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class WelcomeAgent(BaseAgent):
    with open(os.path.join(BASE_DIR, "prompt.md"), "r") as file:
        instruction = file.read()
    
    def __init__(self, state: CallState, instructions: str | None = None) -> None:
        agent_instructions = instructions if instructions is not None else self.instructions_base.format(state=state) + self.instruction.format(state=state)
        super().__init__(state=state, instructions= agent_instructions)
        self.state = state

    @function_tool
    async def set_speaker_name(self, speaker_name: str | None) -> Agent | str:
        """Saves the first name of the one answering the call.
        Always call this tool.
        If no confirmation is given, pass "None".
        Args:
            speaker_name (str | None): The name of the person you are talking to.
        """
        self.state.speaker_name = speaker_name
        if speaker_name == self.state.client_name:
            return PidAgent(state=self.state)
        
    async def on_enter(self):
        print("Welcome Agent ON")
        # self.session.say(f"Olá, sou a atendente virtual da {self.state.enterprise_name}. Estou falando com {self.state.client_name}?", allow_interruptions=False)
        return await super().on_enter()
    
