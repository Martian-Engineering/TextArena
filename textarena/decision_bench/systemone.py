"""Choice-question adapter for Jev-compatible decision model endpoints."""

from __future__ import annotations

import json
import os
import urllib.request
from urllib.parse import urlsplit, urlunsplit

from .runner import Decision


class SystemOnePolicy:
    def __init__(
        self,
        *,
        name: str,
        endpoint: str,
        model: str,
        api_key_env: str,
        timeout: float = 30,
    ):
        self.name = name
        self.endpoint = endpoint
        self.model = model
        self.api_key_env = api_key_env
        self.timeout = timeout

    def metadata(self) -> dict:
        parsed = urlsplit(self.endpoint)
        host = parsed.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        return {
            "kind": "systemone",
            "model": self.model,
            "endpoint": urlunsplit((parsed.scheme, host, parsed.path, "", "")),
        }

    def decide(self, observation: str, actions: tuple[str, ...]) -> Decision:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise ValueError(f"{self.api_key_env} is required")
        payload = {
            "model": self.model,
            "state": {"observation": observation},
            "questions": {
                "action": {
                    "type": "choice",
                    "instructions": "Choose one move for the current game state.",
                    "criteria": {
                        action: f"Move {action.lower()}" for action in actions
                    },
                }
            },
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.load(response)
        answer = body["answers"]["action"]["choice"]
        usage = body.get("usage") or {}
        return Decision(
            action=answer,
            input_tokens=usage.get("input_tokens", usage.get("inputTokens", 0)),
            output_tokens=usage.get("output_tokens", usage.get("outputTokens", 0)),
        )
