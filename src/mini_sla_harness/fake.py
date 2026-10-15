"""Deterministic in-memory responses; no network, credentials, models or scores."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoRecord:
    case_id: str
    prompt: str
    response: str
    provider: str = "deterministic-fake-v1"


CASES = (
    ("sum", "Add 2, 3 and 5.", "10"),
    ("sort", "Sort 3, 1 and 2 ascending.", "1,2,3"),
    ("unicode", "Echo: 你好，Mini-SLA", "你好，Mini-SLA"),
)


class FakeProvider:
    """Return a known fixture and fail explicitly for an unsupported prompt."""

    def complete(self, prompt: str) -> str:
        for _, known_prompt, response in CASES:
            if prompt == known_prompt:
                return response
        raise ValueError("Unsupported fake prompt")
