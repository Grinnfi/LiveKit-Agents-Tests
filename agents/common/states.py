from pydantic import BaseModel, field_validator, ValidationError
from typing import ClassVar

class BaseState(BaseModel):
    """Base State Class"""
    enterprise_name: str = "empresa"

class ClientState(BaseState):
    """Base Client Class"""
    client_name: str
    client_cpf: str

    # CPF validation logic
    @field_validator('client_cpf', mode='before')
    @classmethod
    def normalize_cpf(cls, v: str) -> str:
        v = str(v).replace('.', '').replace('-', '').strip()
        if len(v) != 11:
            raise ValueError(f'CPF must have exactly 11 numbers but got {len(v)}')
        if not v.isdigit():
             raise ValueError('CPF must contain only digits (when unformatted).')
        return v
    
class CallState(ClientState):
    """Live call - speaker_name to account for an unexpected person answering."""
    speaker_name: str | None = None
    
    def get_name(self) -> str:
        return self.speaker_name if self.speaker_name else self.client_name