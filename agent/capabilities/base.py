from abc import ABC, abstractmethod

class Capability(ABC):
    @abstractmethod
    async def can_handle(self, short_term_memory) -> bool:
        pass

    @abstractmethod
    async def get_decision(self, short_term_memory) -> dict:
        pass
