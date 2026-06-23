from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping


@dataclass(frozen=True)
class RLTransition:
    """DDQN-ready single-agent transition for leader and follower replay buffers."""

    episode: int
    step: int
    agent_id: str
    agent_family: str
    observation: Mapping[str, Any]
    action_index: int
    reward: float
    next_observation: Mapping[str, Any]
    done: bool
    info: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "episode": int(self.episode),
            "step": int(self.step),
            "agent_id": str(self.agent_id),
            "agent_family": str(self.agent_family),
            "observation": dict(self.observation),
            "action_index": int(self.action_index),
            "reward": float(self.reward),
            "next_observation": dict(self.next_observation),
            "done": bool(self.done),
            "info": dict(self.info),
        }
