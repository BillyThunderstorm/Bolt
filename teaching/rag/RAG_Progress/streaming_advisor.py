#!/usr/bin/env python3
"""
Streaming Setup Advisor - Helps plan streaming setup based on user goals, budget, and current gear.
"""

import dspy


def setup_model(model_name="gemma4:latest"):
    """Configure the DSPy language model"""
    lm = dspy.LM(
        model=f"ollama/{model_name}",
        api_base="http://localhost:11434",
        api_key="ollama",
    )
    dspy.settings.configure(lm=lm)
    return lm


def test_streaming_advisor():
    """Test a streaming setup advisor that gives recommendations"""

    print("Testing Streaming Setup Advisor")
    print("=" * 50)

    # Setup model - use gemma4 for speed
    setup_model("gemma4:latest")

    # Define signature for streaming advice
    class StreamAdvice(dspy.Signature):
        """Provide streaming setup recommendations based on user inputs"""

        current_setup = dspy.InputField(
            desc="What equipment/software the user currently has (can be 'none' for beginner)"
        )
        budget = dspy.InputField(
            desc="Budget for upgrades (e.g., '$0-100', '$100-500', '$500+', or 'no budget')"
        )
        goals = dspy.InputField(
            desc="Streaming goals (e.g., 'grow audience', 'improve quality', 'start streaming', 'specific game/content')"
        )
        platform = dspy.InputField(desc="Target platform (Twitch, YouTube, Kick, etc.)")

        # Output recommendations
        priority_upgrades = dspy.OutputField(
            desc="Top 1-3 most impactful upgrades or changes within budget"
        )
        settings_optimization = dspy.OutputField(
            desc="Key OBS/streamlabs settings to adjust for better quality/performance"
        )
        engagement_tips = dspy.OutputField(
            desc="Specific tips to increase viewer engagement and retention"
        )
        quick_wins = dspy.OutputField(
            desc="Easy, immediate improvements that cost little or nothing"
        )
        avoidance = dspy.OutputField(
            desc="Common mistakes to avoid for someone at this level"
        )

    # Create the advisor
    advisor = dspy.ChainOfThought(StreamAdvice)

    # Test cases representing different streamer profiles
    test_cases = [
        {
            "current_setup": "Laptop with built-in mic and webcam, no extra equipment",
            "budget": "$0-100",
            "goals": "Start streaming and learn basics",
            "platform": "Twitch",
        },
        {
            "current_setup": "Desktop PC, Logitech C920 webcam, Blue Yeti microphone",
            "budget": "$100-500",
            "goals": "Improve stream quality and grow to affiliate",
            "platform": "Twitch",
        },
        {
            "current_setup": "None (planning to start)",
            "budget": "$500+",
            "goals": "Stream Nintendo Switch games with facecam",
            "platform": "YouTube Gaming",
        },
    ]

    print("\nGenerating streaming setup advice:")
    print("=" * 50)

    for i, case in enumerate(test_cases, 1):
        print(f"\n--- Advice {i} ---")
        print(f"Current: {case['current_setup']}")
        print(f"Budget: {case['budget']}")
        print(f"Goals: {case['goals']}")
        print(f"Platform: {case['platform']}")
        print("-" * 40)

        try:
            result = advisor(
                current_setup=case["current_setup"],
                budget=case["budget"],
                goals=case["goals"],
                platform=case["platform"],
            )

            print(f"🔧 Priority Upgrades:\n{result.priority_upgrades}")
            print(f"\n⚙️ Settings Optimization:\n{result.settings_optimization}")
            print(f"\n💬 Engagement Tips:\n{result.engagement_tips}")
            print(f"\n⚡ Quick Wins:\n{result.quick_wins}")
            print(f"\n⚠️ Avoid:\n{result.avoidance}")

        except Exception as e:
            print(f"Error: {e}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 50)
    print("Streaming Advisor test complete!")
    print("Next steps could include:")
    print("1. Adding equipment database for specific recommendations")
    print("2. Creating troubleshooting guides")
    print("3. Building a content planning module for stream topics")
    print("4. Implementing upgrade path planning over time")
    print("=" * 50)


if __name__ == "__main__":
    test_streaming_advisor()
