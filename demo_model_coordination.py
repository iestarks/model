"""Run a short live demo of local model coordination."""

from __future__ import annotations

import argparse
import builtins
import os

from ollama_model_gate import OllamaModelGate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--choice",
        type=int,
        help="Select a menu entry automatically instead of waiting for terminal input.",
    )
    args = parser.parse_args()
    os.environ["OLLAMA_MAX_LOADED_MODELS"] = "1"
    gate = OllamaModelGate()

    print("=== Current state ===")
    print(gate.status())
    print("=== Routing ===")
    tasks = (
        "summarize this note",
        "fix this Python bug",
        "perform a thorough high-token architecture analysis",
    )
    for task in tasks:
        print(f"{task} -> {gate.route_model(task)}")

    requested = gate.route_model(tasks[-1])[0]
    print(f"Requested: {requested}")
    if args.choice is not None:
        original_input = builtins.input
        builtins.input = lambda _prompt: str(args.choice)
        try:
            selected = gate.select_model(requested)
        finally:
            builtins.input = original_input
    else:
        selected = gate.select_model(requested)
    print(f"Selected: {selected}")
    print("=== Final state ===")
    print(gate.status())


if __name__ == "__main__":
    main()