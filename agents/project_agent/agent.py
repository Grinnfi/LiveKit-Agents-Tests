import os
# from livekit.agents import function_tool
from agents.common.states import CallState
from agents.common.agent import BaseAgent

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PROJECT_STATUS = "O projeto está em construção" # would get info from some db

class ProjectAgent(BaseAgent):
    with open(os.path.join(BASE_DIR, "prompt.md"), "r") as file:
        instruction = file.read().format(project_status= PROJECT_STATUS)
    
    def __init__(self, state: CallState, instructions: str | None = None) -> None:
        agent_instructions = instructions if instructions is not None else self.instructions_base.format(state=state) + self.instruction.format(state=state)
        super().__init__(state=state, instructions= agent_instructions)
        self.state = state

    async def on_enter(self):
        self.session.generate_reply()
        return await super().on_enter()