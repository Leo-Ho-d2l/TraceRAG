from __future__ import annotations

import argparse

from app.db.session import SessionLocal
from app.services.chat import ChatService

from app.core.event_loop import run_async


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--mode", choices=["auto", "retrieve", "research"], default="auto")
    args = parser.parse_args()

    async with SessionLocal() as session:
        result = await ChatService(session).answer(args.question, None, args.mode, 6)
        print(result.answer)
        if result.citations:
            print("\nSources:")
            for citation in result.citations:
                print(f"[{citation.label}] {citation.filename} — {citation.section_title or ''}")
        if result.tool_trace:
            print("\nTool trace:")
            for event in result.tool_trace:
                print(event.model_dump())


if __name__ == "__main__":
    run_async(main())
