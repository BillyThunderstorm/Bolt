#!/usr/bin/env python3
"""
Streaming Assistant - A helpful tool for streamers to get quick advice on common issues.
Designed to be fast, practical, and easy to use.
"""

import dspy
import sys


def setup_streaming_assistant(model_name="gemma4:latest"):
    """Initialize the streaming assistant with a specified model"""
    try:
        lm = dspy.LM(
            model=f"ollama/{model_name}",
            base_url="http://localhost:11434",
            api_key="ollama",
        )
        dspy.settings.configure(lm=lm)
        return True, f"Initialized with {model_name}"
    except Exception as e:
        return False, f"Failed to initialize: {e}"


def get_streaming_tip(situation):
    """
    Get a quick, practical tip for a streaming situation.

    Args:
        situation (str): The streaming problem or situation

    Returns:
        str: A practical tip to address the situation
    """

    class StreamTip(dspy.Signature):
        """Give a quick streaming tip for a specific situation"""

        situation = dspy.InputField(desc="Streaming situation or problem")
        tip = dspy.OutputField(
            desc="One practical, actionable tip to improve the situation"
        )

    try:
        predictor = dspy.Predict(StreamTip)
        result = predictor(situation=situation)
        return result.tip.strip()
    except Exception as e:
        return f"Error getting advice: {e}"


def get_streaming_setup_advice(current_setup, budget, goals, platform="Twitch"):
    """
    Get streaming setup recommendations (more detailed advice).

    Args:
        current_setup (str): Current equipment/software
        budget (str): Budget range for upgrades
        goals (str): Streaming goals
        platform (str): Target streaming platform

    Returns:
        dict: Advice categories or error message
    """

    class StreamAdvice(dspy.Signature):
        """Provide streaming setup recommendations"""

        current_setup = dspy.InputField(
            desc="Current equipment/software (can be 'none')"
        )
        budget = dspy.InputField(
            desc="Budget for upgrades (e.g., '$0-100', '$100-500', '$500+')"
        )
        goals = dspy.InputField(
            desc="Streaming goals (e.g., 'grow audience', 'improve quality')"
        )
        platform = dspy.InputField(desc="Target platform (Twitch, YouTube, etc.)")

        priority_upgrades = dspy.OutputField(
            desc="Top 1-3 most impactful upgrades within budget"
        )
        settings_optimization = dspy.OutputField(
            desc="Key OBS/streamlabs settings to adjust"
        )
        engagement_tips = dspy.OutputField(desc="Tips to increase viewer engagement")
        quick_wins = dspy.OutputField(desc="Easy, immediate improvements (low/no cost)")
        avoid_mistakes = dspy.OutputField(desc="Common mistakes to avoid at this level")

    try:
        advisor = dspy.ChainOfThought(StreamAdvice)
        result = advisor(
            current_setup=current_setup, budget=budget, goals=goals, platform=platform
        )

        return {
            "priority_upgrades": result.priority_upgrades.strip(),
            "settings_optimization": result.settings_optimization.strip(),
            "engagement_tips": result.engagement_tips.strip(),
            "quick_wins": result.quick_wins.strip(),
            "avoid_mistakes": result.avoid_mistakes.strip(),
        }
    except Exception as e:
        return {"error": f"Error getting setup advice: {e}"}


def main():
    """Main function to run the streaming assistant"""
    print("🎥 Streaming Assistant - Your Twitch/YouTube Helper")
    print("=" * 55)
    print("Get quick advice for streaming problems and setup questions.")
    print("Type 'quit' or 'exit' to stop.\n")

    # Initialize the assistant
    success, msg = setup_streaming_assistant("gemma4:latest")  # Fastest model
    if not success:
        print(f"❌ {msg}")
        print("Make sure Ollama is running: ollama serve")
        return

    print(f"✅ {msg}")
    print("\nChoose how you want help:")
    print("1. Quick tip for a specific problem (fast)")
    print("2. Detailed setup advice (more detailed, takes longer)")
    print("3. See examples of what you can ask")
    print("4. Quit\n")

    while True:
        try:
            choice = input("What would you like to do? (1-4): ").strip()

            if choice.lower() in ["quit", "exit", "4"]:
                print("\n👋 Happy streaming! Keep creating great content.")
                break

            elif choice == "1":
                print("\n💡 Quick Tip Mode - Describe your streaming problem")
                print(
                    "Examples: 'My audio sounds echoey', 'I'm not getting chat interaction', 'Webcam too dark'"
                )
                situation = input("\nDescribe your situation: ").strip()

                if not situation:
                    print("Please describe your situation.")
                    continue

                print("\n🔍 Getting your tip...")
                tip = get_streaming_tip(situation)
                print(f"\n💡 Tip: {tip}\n")

            elif choice == "2":
                print("\n🛠️ Setup Advice Mode - Tell me about your current setup")
                current = input(
                    "Current setup (e.g., 'laptop with built-in mic', 'none'): "
                ).strip()
                if not current:
                    current = "none"

                budget = input(
                    "Budget for upgrades (e.g., '$0-100', '$100-500', '$500+'): "
                ).strip()
                if not budget:
                    budget = "$0-100"

                goals = input(
                    "Your goals (e.g., 'start streaming', 'improve quality', 'grow to affiliate'): "
                ).strip()
                if not goals:
                    goals = "start streaming and have fun"

                platform = (
                    input("Platform (Twitch, YouTube, Kick, etc.) [Twitch]: ").strip()
                    or "Twitch"
                )

                print("\n🔧 Getting your setup advice (this may take a moment)...")
                advice = get_streaming_setup_advice(current, budget, goals, platform)

                if "error" in advice:
                    print(f"\n❌ {advice['error']}\n")
                else:
                    print(f"\n🎯 PRIORITY UPGRADES:\n{advice['priority_upgrades']}")
                    print(
                        f"\n⚙️ SETTINGS OPTIMIZATION:\n{advice['settings_optimization']}"
                    )
                    print(f"\n💬 ENGAGEMENT TIPS:\n{advice['engagement_tips']}")
                    print(f"\n⚡ QUICK WINS:\n{advice['quick_wins']}")
                    print(f"\n⚠️ AVOID THESE MISTAKES:\n{advice['avoid_mistakes']}\n")

            elif choice == "3":
                print("\n📝 EXAMPLES OF WHAT YOU CAN ASK:")
                print("\nQuick Tip Examples:")
                print("  • 'My stream keeps dropping frames'")
                print("  • 'I don't know what game to play next'")
                print("  • 'My voice sounds muffled on stream'")
                print("  • 'How to make my overlays less distracting'")
                print("  • 'My chat is always silent, how to fix that'")

                print("\nSetup Advice Examples:")
                print("  • Current: 'none', Budget: '$0-100', Goals: 'start streaming'")
                print(
                    "  • Current: 'Blue Yeti mic, laptop webcam', Budget: '$100-500', Goals: 'improve quality'"
                )
                print(
                    "  • Current: 'Desktop PC, no mic', Budget: '$500+', Goals: 'go full-time'"
                )
                print()

            else:
                print("Please choose 1, 2, 3, or 4.\n")

        except KeyboardInterrupt:
            print("\n\n👋 Happy streaming! Keep creating great content.")
            break
        except Exception as e:
            print(f"\n❌ An error occurred: {e}")
            print("Please try again.\n")


if __name__ == "__main__":
    main()
