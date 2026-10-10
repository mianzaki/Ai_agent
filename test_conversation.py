"""Smoke-test that consecutive Pipecat/Ollama turns retain bounded context."""

import asyncio

from bot import run_agent


async def main() -> int:
    history: list[dict[str, str]] = []
    first, _ = await run_agent(
        "Remember this test word for my next question: cobalt. Reply briefly.",
        history=history,
    )
    if not first:
        print("Conversation smoke failed: first turn returned no text.")
        return 1
    history.extend(
        [
            {
                "role": "user",
                "content": "Remember this test word for my next question: cobalt. Reply briefly.",
            },
            {"role": "assistant", "content": first},
        ]
    )

    second, _ = await run_agent("What was the test word? Reply with the word only.", history=history)
    if "cobalt" not in second.casefold():
        print(f"Conversation smoke failed: prior-turn fact was not recalled: {second!r}")
        return 1
    print("Conversation smoke passed: the second Pipecat turn recalled 'cobalt'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
