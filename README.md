Sistema multiagêntico de voz com LiveKit agents.

-> Agentes separados nas pastas "agents" com seus devidos prompts. 
-> Herança de agentes: Agentes usam a prompt e tools de quem herdaram, adicionando suas prórias prompts em baixo. (facilita manutenção)

Infos do cliente são passadas no main.py em client_data.

3 Agentes como poc:
Welcome: Verifica nome e passa para PID 
PID (personal identifiable data): Verifica cpf e passa para project.
Project: Fala sobre a situação do projeto atual.  

Use "python main.py console" para rodar no terminal.

Após inicialização, pode dar ctrl + b para digitar invés de falar (útil para testes)