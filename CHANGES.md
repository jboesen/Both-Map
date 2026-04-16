# Minimax Integration - Changes Summary

## What Was Done

Fixed Minimax API compatibility issues by creating a unified LLM client that works with both Anthropic and Minimax APIs.

## Files Created

1. **`services/llm_client.py`** - New unified client that:
   - Auto-detects Anthropic vs Minimax based on `ANTHROPIC_BASE_URL`
   - Uses Anthropic SDK for Anthropic
   - Uses direct HTTP calls for Minimax
   - Translates Minimax's OpenAI-style responses to Anthropic format
   - Provides a consistent `create_message()` interface

2. **`test_minimax_simple.py`** - Simple test script to verify your setup works

3. **`test_minimax_all.py`** - Comprehensive test that tries multiple API endpoints/formats

4. **`MINIMAX_SETUP.md`** - Complete setup and troubleshooting guide

## Files Modified

Updated all service files to use the unified client:

1. **`services/research_service.py`**
   - Removed `_anthropic_client()` function
   - Uses `get_client()` from llm_client
   - Changed `client.messages.create()` → `client.create_message()`
   - Changed `message.content[0].text` → `message["content"][0]["text"]`

2. **`services/topic_engine.py`**
   - Same changes as above

3. **`services/profile_service.py`**
   - Same changes as above

4. **`services/audio_service.py`**
   - Same changes as above
   - Renamed client to `llm_client` to avoid conflict with Supabase client

5. **`services/history_ingest_service.py`**
   - Same changes as above

## How It Works

### Environment Variables

**For Minimax:**
```bash
ANTHROPIC_API_KEY=your_minimax_key
ANTHROPIC_BASE_URL=https://api.minimax.chat
ANTHROPIC_MODEL=abab6.5s-chat
```

**For Anthropic:**
```bash
ANTHROPIC_API_KEY=your_anthropic_key
# Leave ANTHROPIC_BASE_URL blank or omit it
```

### Auto-Detection Logic

```python
def _is_minimax():
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
    return "minimax" in base_url.lower()
```

If Minimax is detected:
- Uses HTTP POST to `/v1/text/chatcompletion_v2` (or OpenAI-compatible endpoints as fallback)
- Converts OpenAI-style response `{"choices": [...]}` to Anthropic format `{"content": [...]}`

If Anthropic is detected:
- Uses official `anthropic` SDK
- No conversion needed

## Next Steps

1. **Create `.env` file** with your Minimax credentials:
   ```bash
   cp .env.example .env
   # Then edit .env and add your Minimax key
   ```

2. **Test the integration:**
   ```bash
   python3 test_minimax_simple.py
   ```

3. **If test passes**, you're good to go! Start the server:
   ```bash
   uvicorn main:app --reload
   ```

4. **If test fails**, check the error message and see MINIMAX_SETUP.md for troubleshooting

## Rollback

To switch back to Anthropic:
1. Change `ANTHROPIC_API_KEY` to your Anthropic key
2. Remove `ANTHROPIC_BASE_URL` from .env
3. Restart server

No code changes needed - the unified client handles both!

## Testing Checklist

- [ ] Syntax check passed (all files compile)
- [ ] `.env` configured with Minimax credentials
- [ ] `test_minimax_simple.py` passes
- [ ] Server starts without errors
- [ ] Can generate topics via `/topics` endpoint
- [ ] Can generate posts via `/generate` endpoint
- [ ] Can get profile via `/profile` endpoint

## Deployment

When deploying to Render/Railway:
1. Set environment variables in the dashboard
2. Make sure `ANTHROPIC_BASE_URL=https://api.minimax.chat`
3. Set the correct `ANTHROPIC_MODEL` name
4. Deploy!

The code will automatically use Minimax instead of Anthropic.
