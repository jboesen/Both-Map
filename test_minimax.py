#!/usr/bin/env python3
"""
Quick test script to debug Minimax API calls
"""
import os
import sys
from dotenv import load_dotenv
import anthropic

load_dotenv()

def test_minimax():
    # Print environment config
    print("=== Environment Configuration ===")
    api_key = os.getenv('MINIMAX_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
    base_url = os.getenv('MINIMAX_BASE_URL') or os.getenv('ANTHROPIC_BASE_URL') or 'https://api.minimax.io/anthropic'
    model = os.getenv('MINIMAX_MODEL') or os.getenv('ANTHROPIC_MODEL') or 'MiniMax-M2.7'

    print(f"MINIMAX_API_KEY: {'SET' if api_key else 'NOT SET'}")
    print(f"MINIMAX_BASE_URL: {base_url}")
    print(f"MINIMAX_MODEL: {model}")
    print()

    # Try to create client
    print("=== Creating MiniMax Client (via Anthropic SDK) ===")
    try:
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
            print(f"Using base_url: {base_url}")

        client = anthropic.Anthropic(**kwargs)
        print("✓ Client created successfully")
        print(f"Client base_url: {client.base_url if hasattr(client, 'base_url') else 'N/A'}")
    except Exception as e:
        print(f"✗ Failed to create client: {type(e).__name__}: {e}")
        sys.exit(1)

    # Try a simple API call
    print("\n=== Testing API Call ===")
    print(f"Using model: {model}")

    try:
        message = client.messages.create(
            model=model,
            max_tokens=100,
            messages=[{"role": "user", "content": "Say 'hello' in one word"}],
        )
        print("✓ API call successful!")
        print("\nResponse blocks:")
        for block in message.content:
            if block.type == "thinking":
                print(f"  [Thinking]: {block.thinking[:100]}...")
            elif block.type == "text":
                print(f"  [Text]: {block.text}")
        print("\n✅ SUCCESS! MiniMax API is working correctly.")
    except Exception as e:
        print(f"✗ API call failed: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print(f"\nFull error:")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_minimax()
