import json
import os
import sys

# Data files live at the project root (one level up from this package),
# not inside the installed package itself.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(PROJECT_ROOT, "termio_config.json")

MODELS = {
    "1": {
        "name":     "qwen2.5-coder:3b",
        "label":    "Qwen 2.5 Coder 3B",
        "rating":   "⭐ Recommended",
        "size":     "~2GB",
        "speed":    "Fast",
        "best_for": "Low-end hardware, daily use"
    },
    "2": {
        "name":     "qwen2.5-coder:7b",
        "label":    "Qwen 2.5 Coder 7B",
        "rating":   "🔥 Best Quality",
        "size":     "~4.5GB",
        "speed":    "Medium",
        "best_for": "Better hardware, complex commands"
    },
    "3": {
        "name":     "llama3.2:3b",
        "label":    "Llama 3.2 3B",
        "rating":   "✅ Good",
        "size":     "~2GB",
        "speed":    "Fast",
        "best_for": "General use, lightweight"
    },
    "4": {
        "name":     "mistral:7b",
        "label":    "Mistral 7B",
        "rating":   "✅ Good",
        "size":     "~4.5GB",
        "speed":    "Medium",
        "best_for": "General purpose tasks"
    },
    "5": {
        "name":     "deepseek-coder:6.7b",
        "label":    "DeepSeek Coder 6.7B",
        "rating":   "💡 Decent",
        "size":     "~4GB",
        "speed":    "Medium",
        "best_for": "Code-heavy tasks"
    },
    "6": {
        "name":     "codellama:7b",
        "label":    "CodeLlama 7B",
        "rating":   "⚠️  Okay",
        "size":     "~4.5GB",
        "speed":    "Slow",
        "best_for": "Not recommended for Termio"
    },
}

def print_model_table():
    print()
    print(f"  {'#':<4} {'Model':<28} {'Rating':<22} {'Size':<8} {'Speed':<10} {'Best For'}")
    print("  " + "-" * 95)
    for key, m in MODELS.items():
        print(f"  {key:<4} {m['label']:<28} {m['rating']:<22} {m['size']:<8} {m['speed']:<10} {m['best_for']}")
    print()

def run_setup():
    print()
    print("=" * 50)
    print("       Welcome to Termio — First Run Setup")
    print("=" * 50)

    os_type = "linux"
    os_label = "Linux (Bash)"

    # ── Model Selection ───────────────────────────────
    print(f"\nChoose your Ollama model:\n")
    print_model_table()
    print("  💡 Tip: On low-end hardware (4GB RAM or less) pick option 1 or 3.")
    print("  💡 Tip: On 8GB+ RAM pick option 2 for better results.")
    print()

    while True:
        try:
            choice = input("Enter number (1-6) or type a custom model name: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSetup cancelled.\n")
            sys.exit(1)
        if choice in MODELS:
            model = MODELS[choice]["name"]
            model_label = MODELS[choice]["label"]
            break
        elif choice and " " not in choice:
            model = choice
            model_label = choice
            break
        else:
            print("Invalid choice. Enter a number between 1 and 6 or a valid model name.\n")

    # ── Save Config ───────────────────────────────────
    config = {"model": model, "os": os_type}
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

    print()
    print(f"✅ OS set to:    {os_label}")
    print(f"✅ Model set to: {model_label}")
    print()
    print("Make sure to pull your model if you have not already:")
    print(f"  ollama pull {model}")
    print()
    try:
        input("Press Enter to start Termio...")
    except (EOFError, KeyboardInterrupt):
        pass
    print()
    return config

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return run_setup()
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def reset_config():
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)
    return run_setup()