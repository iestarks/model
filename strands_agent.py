import os
import subprocess
import getpass
from pathlib import Path

from strands import Agent, tool
from strands.models.ollama import OllamaModel
from model.ollama_model_gate import OllamaModelGate, proxy_headers


def choose_model():
    """Prompt for the model before creating the agent."""
    gate = OllamaModelGate()
    installed = gate.installed_models()
    loaded = gate.loaded_models()
    choices = list(dict.fromkeys(loaded + installed))
    fastest = max(
        (
            model_name
            for model_name in choices
            if gate.profile(model_name)["role"] != "embeddings only"
        ),
        key=lambda model_name: gate.profile(model_name)["speed"],
    )
    default_index = choices.index(fastest) + 1

    print("\nSelect the Ollama model for this session:")
    for index, model_name in enumerate(choices, start=1):
        marker = " (currently loaded)" if model_name in loaded else ""
        default_marker = " (default)" if model_name == fastest else ""
        profile = gate.profile(model_name)
        print(
            f"  {index}. {model_name}{marker}{default_marker} | "
            f"{profile['size']} | speed {profile['speed']}/5 | quality {profile['quality']}/5 | "
            f"{profile['role']}"
        )

    while True:
        try:
            answer = input(f"Model [1-{len(choices)}, default {default_index}]: ").strip()
            selected = fastest if not answer else choices[int(answer) - 1]
        except (ValueError, IndexError):
            print("Enter the number of one model from the list.")
            continue
        print(f"Selected Ollama model: {selected}\n")
        return gate.select_model(selected, prompt_on_conflict=False)

def prompt_sudo_password():
    """Prompt user for sudo password securely."""
    return getpass.getpass("🔐 Sudo password required: ")

def execute_command(cmd, use_sudo=False, password=None):
    """Execute a shell command with optional sudo elevation."""
    try:
        if use_sudo:
            if password is None:
                password = prompt_sudo_password()
            # Use echo to pipe password to sudo
            full_cmd = f"echo '{password}' | sudo -S {cmd}"
            result = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
        else:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
        
        if result.returncode != 0:
            return f"❌ Command failed:\n{result.stderr}"
        return result.stdout if result.stdout else "✅ Command executed successfully"
    
    except subprocess.TimeoutExpired:
        return "❌ Command timed out (30s limit)"
    except Exception as e:
        return f"❌ Error: {str(e)}"


@tool
def list_local_github_repo_names() -> str:
    """List local development folders that contain a .git directory."""
    development_dir = Path.home() / "development"
    repositories = sorted(
        path.name
        for path in development_dir.iterdir()
        if path.is_dir() and (path / ".git").is_dir()
    )
    return "\n".join(repositories) if repositories else "No local Git repositories found."


def is_repository_listing_request(user_input: str) -> bool:
    normalized = user_input.lower()
    return "github" in normalized and any(
        phrase in normalized
        for phrase in ("repo", "repository")
    ) and any(
        phrase in normalized
        for phrase in ("list", "show", "folder", "directory", "name")
    )

def main():
    selected_model = choose_model()

    # 1. Configure the local model provider
    model_provider = OllamaModel(
        host=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        model_id=selected_model,
        ollama_client_args={"headers": proxy_headers()},
    )

    # 2. Create agent with admin capabilities
    agent = Agent(
        name="MacOSAdmin",
        model=model_provider,
        system_prompt=(
            "You are a macOS system administration assistant. You can help users "
            "manage their system, install packages, configure settings, and perform "
            "admin tasks. For read-only requests, answer directly and do not ask for "
            "confirmation. Use list_local_github_repo_names when asked to list local "
            "GitHub repositories. For admin operations that change the system, ask "
            "for confirmation and explain the risks."
        ),
        tools=[list_local_github_repo_names],
    )

    # 3. Track sudo password for the session
    sudo_password = None
    
    # 4. Start interactive chat loop
    print("🤖 Strands macOS Admin Agent")
    print("=" * 60)
    print("I can help with macOS administration, system commands, and configs.")
    print("Type 'help' for available commands, 'exit' to quit.")
    print("=" * 60 + "\n")

    while True:
        try:
            user_input = input("You: ").strip()
            
            if not user_input:
                continue

            if is_repository_listing_request(user_input):
                print("\nLocal GitHub repository folders:")
                print(list_local_github_repo_names())
                print()
                continue
            
            # Handle special commands
            if user_input.lower() == "help":
                print("\n📖 Available Commands:")
                print("  sudo <command>     - Run command with admin privileges")
                print("  shell <command>    - Run regular shell command")
                print("  clear_sudo         - Clear cached sudo password")
                print("  exit/quit/bye      - Exit the agent\n")
                continue
            
            if user_input.lower() == "clear_sudo":
                sudo_password = None
                print("✅ Sudo password cleared.\n")
                continue
            
            if user_input.lower() in {"exit", "quit", "bye"}:
                print("\nAgent: Goodbye! Session ended.\n")
                break
            
            # Check for explicit sudo or shell commands
            if user_input.lower().startswith("sudo "):
                cmd = user_input[5:].strip()
                print(f"\n⚠️  Admin command requested: sudo {cmd}")
                confirm = input("Execute? (y/n): ").strip().lower()
                
                if confirm == "y":
                    if sudo_password is None:
                        sudo_password = prompt_sudo_password()
                    result = execute_command(cmd, use_sudo=True, password=sudo_password)
                    print(f"Result:\n{result}\n")
                else:
                    print("❌ Command cancelled.\n")
                continue
            
            if user_input.lower().startswith("shell "):
                cmd = user_input[6:].strip()
                result = execute_command(cmd, use_sudo=False)
                print(f"Result:\n{result}\n")
                continue
            
            # Otherwise, ask the agent
            print(
                "\nAgent is processing your request. Large models may take a minute...",
                flush=True,
            )
            print("Agent: ", end="", flush=True)
            response = agent(user_input)
            print(response)
            print()
            
        except KeyboardInterrupt:
            print("\n\nAgent: Session interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")

if __name__ == "__main__":
    main()

