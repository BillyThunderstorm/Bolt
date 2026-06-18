#!/usr/bin/env python3
"""
Simple Streaming Helper - Quick tips for streamers
"""

import dspy


def setup_model(model_name="gemma4:latest"):
    """Configure the DSPy language model"""
    lm = dspy.LM(
        model=f"ollama/{model_name}",
        base_url="http://localhost:11434",
        api_key="ollama",
    )
    dspy.settings.configure(lm=lm)
    return lm


def test_simple_streaming_helper():
    """Test a simple streaming helper that gives quick tips"""

    print("Testing Simple Streaming Helper")
    print("=" * 40)

    # Setup model - use gemma4 for speed
    setup_model("gemma4:latest")

    # Define a simple signature
    class StreamTip(dspy.Signature):
        """Give a quick streaming tip"""

        situation = dspy.InputField(desc="Streaming situation or problem")
        tip = dspy.OutputField(desc="One practical tip to improve the situation")

    # Create the helper
    helper = dspy.Predict(StreamTip)

    # Test situations
    situations = [
        "My audio sounds echoey when I stream",
        "My stream keeps dropping frames",
        "I'm not getting enough interaction from viewers",
        "My webcam looks too dark",
        "I don't know what to play next to grow my channel",
    ]

    print("\nGetting streaming tips:")
    print("-" * 40)

    for situation in situations:
        print(f"\nSituation: {situation}")
        try:
            result = helper(situation=situation)
            print(f"Tip: {result.tip}")
        except Exception as e:
            print(f"Error: {e}")

    print("\n" + "=" * 40)
    print("Simple helper test complete!")


if __name__ == "__main__":
    test_simple_streaming_helper()
