"""
AdversarialIQ Agentic Fast-Forward Simulation Package
Implements zero-lookahead historical replay, multi-turn Bull vs Bear debates,
persistent private/session/day memories, and local 2-way paper execution.
"""

from .adversarial_debate import AdversarialDebateEngine
from .historical_store import HistoricalMarketStore
from .sim_broker import SimulationBroker
from .sim_memory import SimulationMemory
from .simulator import AgenticTradingSimulator

__all__ = [
    "HistoricalMarketStore",
    "SimulationMemory",
    "SimulationBroker",
    "AdversarialDebateEngine",
    "AgenticTradingSimulator",
]
