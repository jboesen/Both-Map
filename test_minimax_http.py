#!/usr/bin/env python3
"""
Test MiniMax API using raw HTTP to see exact request/response.
"""
import os
import requests
import json

API_KEY = os.getenv('ANTHROPIC_API_KEY')
BASE_URL = os.getenv('ANTHROPIC_BASE_URL', 'https://api.minimax.chat')

print(f"API Key: {API_KEY[:20]}...")
print(f"Base URL: {BASE_URL}")
print()

# Try different endpoint paths
test_endpoints = [
    f"{BASE_URL}/v1/messages",
    f"{BASE_URL}/messages",
    f"{BASE_URL}/v1/chat/completions",
    f"{BASE_URL}/chat/completions",
]

headers = {
    "x-api-key": API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json"
}

payload = {
    "model": "MiniMax-M2.5",
    "max_tokens": 10,
    "messages": [
        {"role": "user", "content": "Hi"}
    ]
}

for endpoint in test_endpoints:
    print(f"Testing: {endpoint}")
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=10)
        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.text[:200]}")
        if response.status_code == 200:
            print("  ✅ SUCCESS!")
            break
    except Exception as e:
        print(f"  ❌ Error: {e}")
    print()
