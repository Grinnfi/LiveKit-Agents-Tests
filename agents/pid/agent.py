import logging
import re # change llm output
import os

from typing import AsyncIterable, AsyncGenerator, ClassVar

from livekit.agents import (
    Agent,
    function_tool,
)

from agents.common.states import CallState
from agents.common.agent import BaseAgent
from agents.project_agent.agent import ProjectAgent

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class PidAgent(BaseAgent):
    with open(os.path.join(BASE_DIR, "prompt.md"), "r") as file:
        instruction = file.read()

    def __init__(self, state: CallState, instructions: str | None = None) -> None:
        agent_instructions = instructions if instructions is not None else self.instructions_base.format(state=state) + self.instruction.format(state=state)
        super().__init__(state=state, instructions= agent_instructions)
        self.state = state

    @function_tool
    async def check_cpf(
        self,
        digits: str
        ) -> Agent | str:
        """Checa se os ultimos dígitos do cpf informado é valido. Pode receber mais digitos e tratar de acordo.
        Args:
            digits: Dígitos do cpf.
        """

        self.logger.info(f"Checando dígitos {digits}.")

        if len(digits) > 3:
            digits = digits[-3:]
            self.logger.info(f"Checando dígitos {digits}.")


        if digits == self.state.client_cpf[-3:]:
            self.logger.info("Cliente autenticado")
            self.session.say("Obrigado!")
            return ProjectAgent(state=self.state) # transferindo para agente
        else:
            self.logger.info("Falha ao autentificar cpf.")
            self.session.say("Incorreto, tente novamente.")
            return "Falha ao autentificar cpf."
         
    async def on_enter(self):
        print("PID agenet ON")
        self.session.say(f"Para confirmar sua identidade, pode me dizer os últimos 3 dígitos do seu cpf?!", allow_interruptions=False)
        return await super().on_enter()
    