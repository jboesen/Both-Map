# Minimax Integration Guide

The Both-Map backend now supports Minimax as an alternative to Anthropic's Claude API. This allows you to use Minimax's models while maintaining the same codebase.

## What Changed

We've created a **unified LLM client** (`services/llm_client.py`) that:
- Auto-detects whether you're using Anthropic or Minimax based on environment variables
- Translates between Minimax's API format and Anthropic's SDK format
- Provides a consistent interface across all service files

All service files have been updated to use this unified client:
- `services/research_service.py`
- `services/topic_engine.py`
- `services/profile_service.py`
- `services/audio_service.py`
- `services/history_ingest_service.py`

## Configuration

### Option 1: Use Minimax

Create a `.env` file with:

```bash
# Minimax Configuration
ANTHROPIC_API_KEY=your_minimax_api_key_here
ANTHROPIC_BASE_URL=https://api.minimax.chat
ANTHROPIC_MODEL=abab6.5s-chat

# Required for other features
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_key
EXA_API_KEY=your_exa_key

# Optional
ELEVENLABS_API_KEY=your_elevenlabs_key
```

### Option 2: Use Anthropic Claude

Create a `.env` file with:

```bash
# Anthropic Configuration
ANTHROPIC_API_KEY=your_anthropic_api_key_here
# Leave ANTHROPIC_BASE_URL blank or omit it entirely
# ANTHROPIC_MODEL=claude-sonnet-4-20250514  # optional, this is the default

# Required for other features
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_key
EXA_API_KEY=your_exa_key

# Optional
ELEVENLABS_API_KEY=your_elevenlabs_key
```

## Testing Your Setup

### Quick Test

Run the simple test script:

```bash
python3 test_minimax_simple.py
```

This will:
1. Load your `.env` configuration
2. Create the unified client
3. Make a test API call
4. Show the response

### Full API Test (All Endpoints)

If the simple test fails, run the comprehensive test to see which API format works:

```bash
python3 test_minimax_all.py
```

This tests multiple authentication methods and endpoints to help debug connection issues.

## How It Works

### Auto-Detection

The unified client detects Minimax in two ways:

1. **Base URL check**: If `ANTHROPIC_BASE_URL` contains "minimax"
2. **Explicit provider**: Set `LLM_PROVIDER=minimax` (optional)

### API Translation

**Minimax API format** (OpenAI-compatible):
```json
POST https://api.minimax.chat/v1/text/chatcompletion_v2
Headers: Authorization: Bearer {api_key}
{
  "model": "abab6.5s-chat",
  "messages": [{"role": "user", "content": "..."}],
  "max_tokens": 1000
}

Response:
{
  "choices": [{"message": {"content": "..."}}],
  "usage": {"prompt_tokens": 10, "completion_tokens": 20}
}
```

**Anthropic format** (what our code expects):
```json
{
  "content": [{"type": "text", "text": "..."}],
  "usage": {"input_tokens": 10, "output_tokens": 20}
}
```

The unified client **automatically translates** between these formats, so all existing code continues to work unchanged.

## Supported Minimax Endpoints

The client tries multiple endpoints in order:

1. `/v1/text/chatcompletion_v2` (Minimax native)
2. `/v1/chat/completions` (OpenAI-compatible)
3. `/chat/completions` (fallback)

Most Minimax deployments should work with endpoint #1 or #2.

## Available Minimax Models

Common Minimax models you can use:

- `abab6.5s-chat` - Fast, cost-effective
- `abab6.5-chat` - Standard model
- `abab6.5g-chat` - Higher quality
- `abab6.5t-chat` - Turbo variant

Check Minimax's documentation for the latest model names and capabilities.

## Troubleshooting

### Error: "ANTHROPIC_API_KEY is not set"

- Make sure you have a `.env` file in the Both-Map directory
- Verify the file contains `ANTHROPIC_API_KEY=your_key`
- Try running with `python3 -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('ANTHROPIC_API_KEY'))"` to test

### Error: "Minimax API failed on all endpoints"

- Check your `ANTHROPIC_BASE_URL` is correct: `https://api.minimax.chat`
- Verify your API key is valid
- Ensure you have quota/credits remaining on Minimax
- Try the base URL without `/v1` suffix: `https://api.minimax.chat`

### Error: HTTP 401 Unauthorized

- Your API key is incorrect or expired
- Make sure you're using the Minimax API key, not an Anthropic key

### Error: HTTP 404 Not Found

- The model name might be wrong
- Try `abab6.5s-chat` or check Minimax docs for current model names

### Error: HTTP 429 Rate Limited

- You've exceeded Minimax's rate limits
- Wait a moment and try again
- Consider upgrading your Minimax plan

## Deployment

### Render

Update your environment variables in the Render dashboard:

1. Go to your service → Environment
2. Set:
   - `ANTHROPIC_API_KEY` = your Minimax key
   - `ANTHROPIC_BASE_URL` = `https://api.minimax.chat`
   - `ANTHROPIC_MODEL` = `abab6.5s-chat` (or your preferred model)
3. Save and redeploy

### Railway

Similar process in Railway's environment variables section.

### Docker

Pass environment variables when running:

```bash
docker run -e ANTHROPIC_API_KEY=your_key \
           -e ANTHROPIC_BASE_URL=https://api.minimax.chat \
           -e ANTHROPIC_MODEL=abab6.5s-chat \
           your-image
```

## Rolling Back

To switch back to Anthropic Claude:

1. Set `ANTHROPIC_API_KEY` to your Anthropic key
2. Remove or comment out `ANTHROPIC_BASE_URL` in your `.env`
3. Optionally remove `ANTHROPIC_MODEL` to use the default Claude model
4. Restart the server

No code changes needed!

## Implementation Details

If you want to understand how the unified client works:

1. See `services/llm_client.py` for the implementation
2. The `UnifiedLLMClient` class handles both providers
3. `_create_message_anthropic()` uses the official Anthropic SDK
4. `_create_message_minimax()` uses direct HTTP requests with format translation
5. All service files use `get_client()` instead of creating their own clients

## Support

If you encounter issues:

1. Run `python3 test_minimax_simple.py` to diagnose
2. Check the error message carefully
3. Verify all environment variables are set correctly
4. Consult Minimax's API documentation for model names and endpoints
5. Open an issue with the full error trace if problems persist
