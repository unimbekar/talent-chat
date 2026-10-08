"""Ask the recruiter assistant questions from the shell and print each event.

  uv run python scripts/assistant_probe.py "Java developers in Maryland" "who fits A1001?"

Each argument is one turn of the same conversation. --page sets the page context as JSON.
"""

import argparse
import json
import time

from app.admin.assistant.engine import run_turn
from app.config import get_settings
from app.core.llm import build_llm_client
from app.db import admin_session


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("questions", nargs="+")
    parser.add_argument("--page", default="{}")
    parser.add_argument("--tz", default="America/New_York")
    args = parser.parse_args()
    settings = get_settings()
    llm = build_llm_client(settings.llm_backend, settings.llm_base_url, settings.llm_model, settings.llm_api_key, settings.aws_region)
    history: list[dict] = []
    for question in args.questions:
        history.append({"role": "user", "content": question})
        print(f"\n=== {question}")
        started = time.monotonic()
        answer = ""
        steps: dict[str, dict] = {}
        session = admin_session()
        try:
            for event in run_turn(
                session=session,
                llm=llm,
                embedder=None,
                messages=history,
                page=json.loads(args.page),
                timezone_name=args.tz,
                max_steps=settings.assistant_max_steps,
                model_name=settings.llm_model,
            ):
                kind = event["type"]
                if kind == "token":
                    continue
                if kind == "step":
                    steps[event["id"]] = {"tool": event["tool"], "args": event["args"]}
                    print(f"  → {event['tool']} {json.dumps(event['args'])}")
                elif kind == "step_done":
                    if event["id"] in steps:
                        steps[event["id"]]["summary"] = event["summary"]
                        steps[event["id"]]["memo"] = event.get("memo") or {}
                    print(f"    {'ok' if event['ok'] else 'ERR'} {event['summary']}")
                elif kind == "block":
                    block = event["block"]
                    print(f"    [block {block['type']}] {block.get('title', '')} rows={len(block.get('rows', []))}")
                elif kind == "final":
                    answer = event["text"]
                elif kind == "done":
                    print(f"  done {event['elapsed_ms']} ms tools={event['tools']} usage={event['usage']}")
                else:
                    print("  ", event)
        finally:
            session.close()
        print(f"  ANSWER ({time.monotonic() - started:.1f}s):\n    " + answer.replace("\n", "\n    "))
        history.append({"role": "assistant", "content": answer, "tools": list(steps.values())})


if __name__ == "__main__":
    main()
