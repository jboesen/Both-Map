#!/usr/bin/env python3
"""Simple verification that MiniMax config is correct."""
import os
from dotenv import load_dotenv

load_dotenv()

print("✅ MiniMax Configuration:")
print(f"   API Key: {os.getenv('ANTHROPIC_API_KEY', 'NOT SET')[:20]}...")
print(f"   Base URL: {os.getenv('ANTHROPIC_BASE_URL', 'NOT SET')}")
print(f"   Model: {os.getenv('ANTHROPIC_MODEL', 'NOT SET')}")
print()

# Verify env vars
assert os.getenv('ANTHROPIC_API_KEY'), "❌ ANTHROPIC_API_KEY not set"
assert os.getenv('ANTHROPIC_BASE_URL') == 'https://api.minimax.io/anthropic', \
    f"❌ Wrong base URL: {os.getenv('ANTHROPIC_BASE_URL')}"
assert os.getenv('ANTHROPIC_MODEL') in ['MiniMax-M2.7', 'MiniMax-M2.7-highspeed', 'MiniMax-M2.5'], \
    f"❌ Wrong model: {os.getenv('ANTHROPIC_MODEL')}"

print("✅ Configuration is correct!")
print()
print("Next steps:")
print("1. Add these same env vars to Render dashboard")
print("2. Redeploy your backend")
print("3. Test with: curl https://both-map.onrender.com/topics")
