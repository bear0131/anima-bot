from abc import ABC, abstractmethod

class Capability(ABC):
    @abstractmethod
    async def can_handle(self, context) -> bool:
        pass

    @abstractmethod
    async def get_decision(self, context) -> dict:
        pass
