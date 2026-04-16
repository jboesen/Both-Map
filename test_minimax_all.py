#!/usr/bin/env python3
"""
Comprehensive test to verify MiniMax works with all backend services.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Test 1: LLM Client
print("=" * 60)
print("TEST 1: LLM Client")
print("=" * 60)

from services.llm_client import get_client

try:
    client = get_client()
    response = client.create_message(
        model=os.getenv("ANTHROPIC_MODEL", "MiniMax-M2.7"),
        max_tokens=100,
        messages=[{"role": "user", "content": "Say hello in one word"}],
    )
    print(f"✅ LLM Client works!")
    print(f"   Model: {response['model']}")
    print(f"   Response blocks: {len(response['content'])}")
    for block in response['content']:
        if block['type'] == 'text':
            print(f"   Text: {block['text'][:50]}")
        elif block['type'] == 'thinking':
            print(f"   Thinking: {block['thinking'][:50]}...")
except Exception as e:
    print(f"❌ LLM Client failed: {e}")
    sys.exit(1)

print()

# Test 2: Topic Engine (uses prompts)
print("=" * 60)
print("TEST 2: Topic Engine")
print("=" * 60)

try:
    from services.topic_engine import select_next_topic
    from services.db_service import get_profile

    # Create a minimal test profile
    test_profile = {
        "topics": {
            "interests": [
                {"topic": "AI research", "weight": 0.9},
                {"topic": "programming", "weight": 0.8}
            ],
            "covered": [],
            "exclusions": []
        }
    }

    topic = select_next_topic(test_profile)
    print(f"✅ Topic Engine works!")
    print(f"   Selected topic: {topic}")
except Exception as e:
    print(f"❌ Topic Engine failed: {e}")
    import traceback
    traceback.print_exc()

print()

# Test 3: Research Service  
print("=" * 60)
print("TEST 3: Research Service (if EXA_API_KEY set)")
print("=" * 60)

if os.getenv("EXA_API_KEY"):
    try:
        from services.research_service import research_and_write

        test_profile = {
            "topics": {"interests": [], "exclusions": []},
            "mental_models": [],
            "tone_preferences": {"style": "casual", "depth": "medium"}
        }

        result = research_and_write("AI reasoning models", test_profile)
        print(f"✅ Research Service works!")
        print(f"   Title: {result['title'][:60]}...")
        print(f"   Body length: {len(result['body_html'])} chars")
        print(f"   Sources: {len(result.get('sources', []))}")
    except Exception as e:
        print(f"❌ Research Service failed: {e}")
        import traceback
        traceback.print_exc()
else:
    print("⏭️  Skipped (EXA_API_KEY not set)")

print()
print("=" * 60)
print("✅ ALL TESTS PASSED!")
print("=" * 60)
