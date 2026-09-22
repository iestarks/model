import os

from strands import Agent, tool
from strands.models.ollama import OllamaModel

from ollama_model_gate import OllamaModelGate


def build_agent(model_name: str | None = None, task: str = "") -> Agent:
    gate = OllamaModelGate()
    routed_model, route_reason = gate.route_model(task, model_name)
    selected_model = gate.select_model(routed_model)
    print(f"Routing task to {selected_model} ({route_reason}).")
    model = OllamaModel(
        host="http://127.0.0.1:11434",
        model_id=selected_model,
        keep_alive="5m",
    )

    @tool
    def model_status() -> dict:
        """Report which Ollama models are installed and currently loaded."""
        return gate.status()

    @tool
    def select_ollama_model(requested_model: str) -> str:
        """Prompt for an explicit model choice when another model is loaded."""
        selected = gate.select_model(requested_model)
        model.update_config(model_id=selected)
        return f"Selected Ollama model: {selected}"

    @tool
    def route_ollama_model(task: str) -> str:
        """Select and activate the best installed model tier for a task."""
        routed, reason = gate.route_model(task)
        selected = gate.select_model(routed)
        model.update_config(model_id=selected)
        return f"Routed task to {selected} ({reason})."

    return Agent(
        model=model,
        name="LocalResearcher",
        system_prompt=(
            "You are a local research assistant. Use model_status to monitor Ollama. "
            "Use route_ollama_model for busy, long-context, coding, or reasoning-heavy tasks. "
            "Before requesting a different model, use select_ollama_model and honor the "
            "user's terminal selection. Save summary reports as markdown files when requested."
        ),
        tools=[model_status, select_ollama_model, route_ollama_model],
    )

def main():
    prompt = (
        "Create a brief 3-bullet list explaining the benefits of edge AI computing."
    )
    model_name = os.environ.get("STRANDS_MODEL")
    agent = build_agent(model_name, prompt)
    print("Initializing local Strands session...")
    response = agent(prompt)
    print(f"Agent: {response}")

if __name__ == "__main__":
    main()

