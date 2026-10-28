import json
import sys
import time
from datetime import date

from app.ai.agenda import cost_usd, parse_agenda
from app.config import settings


def main():
    text = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].strip() else sys.stdin.read()

    if not text.strip():
        print("Usage: python -m app.ai.agenda_cli '<text>' or pipe text into stdin", file=sys.stderr)
        sys.exit(1)

    today = date.today()
    tz = "Europe/Kyiv"

    print(f"Parsing agenda with model '{settings.parser_model}'...")
    started = time.monotonic()
    try:
        agenda, usage = parse_agenda(text, today, tz)
    except Exception as exc:
        print(f"Failed to parse agenda ({type(exc).__name__}): {exc}", file=sys.stderr)
        sys.exit(1)

    latency_s = round(time.monotonic() - started, 2)
    cost = cost_usd(settings.parser_model, usage)

    print("\n--- Parsed Agenda (JSON) ---")
    print(json.dumps(agenda.model_dump(mode="json"), indent=2, ensure_ascii=False))
    print("\n--- Metrics ---")
    print(f"Model: {settings.parser_model}")
    print(f"Tokens: in={usage.get('input_tokens')}, out={usage.get('output_tokens')}")
    print(f"Latency: {latency_s}s")
    print(f"Cost: ${cost:.6f}")


if __name__ == "__main__":
    main()
