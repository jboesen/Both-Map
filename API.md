# Substack Autopilot — API Reference

Base URL: `http://localhost:8000` (or your deployed host)

Authentication: none (single-user tool)

All request and response bodies are JSON. All endpoints return `Content-Type: application/json`.

---

## Table of Contents

- [POST /onboard](#post-onboard)
- [POST /enrich-profile](#post-enrich-profile)
- [POST /ingest](#post-ingest)
- [POST /feedback](#post-feedback)
- [GET /profile](#get-profile)
- [PUT /profile](#put-profile)
- [GET /topics](#get-topics)
- [POST /generate](#post-generate)
- [POST /audio](#post-audio)
- [POST /publish](#post-publish)
- [POST /run](#post-run)
- [Data Types](#data-types)
- [Error Responses](#error-responses)

---

## POST /onboard

Scrapes the user's Substack posts and reading history, builds the cognitive profile from scratch, embeds all content into the vector store, and optionally enriches the profile with Perplexity-researched cognitive signals.

Run this once to initialize the system.

### Request

```json
{
  "substack_url": "https://yourname.substack.com",
  "session_cookie": "connect.sid value from an authenticated Substack session",
  "user_info": {
    "name": "Jane Smith",
    "title": "Research Scientist",
    "company": "Acme Corp",
    "twitter": "@janesmith",
    "linkedin": "https://linkedin.com/in/janesmith",
    "academic_background": "PhD Computer Science, MIT",
    "other_urls": ["https://janesmith.com", "https://scholar.google.com/..."]
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `substack_url` | string | yes | Full URL of the user's Substack publication |
| `session_cookie` | string | yes | Value of `connect.sid` cookie from an authenticated Substack.com session. Used to fetch reading history. |
| `user_info` | object | no | Public identity info for Perplexity-based cognitive enrichment. Omit to skip. Requires `PERPLEXITY_API_KEY`. All subfields optional — provide whatever is available. |

### Response

```json
{
  "profile": { ...CognitiveProfile },
  "perplexity_enrichment_ran": true
}
```

| Field | Type | Description |
|---|---|---|
| `profile` | CognitiveProfile | The full profile as built. See [CognitiveProfile](#cognitiveprofile). |
| `perplexity_enrichment_ran` | boolean | Whether Perplexity research ran. False if `user_info` was omitted or `PERPLEXITY_API_KEY` is not set. |

### Notes

- Scrapes up to 50 posts from `{substack_url}/api/v1/archive`
- Perplexity research is discarded after cognitive signal extraction — no raw biographical data is stored
- If Perplexity enrichment fails, the profile from writing/reading analysis is still saved and returned

---

## POST /enrich-profile

Researches the user via Perplexity Sonar and merges extracted cognitive signals (mental models, third-order patterns) into the existing profile. Can be called standalone after initial onboarding — e.g. when you add a new social handle.

Requires `PERPLEXITY_API_KEY`.

### Request

```json
{
  "name": "Jane Smith",
  "title": "Research Scientist",
  "company": "Acme Corp",
  "twitter": "@janesmith",
  "linkedin": "https://linkedin.com/in/janesmith",
  "academic_background": "PhD Computer Science, MIT",
  "other_urls": ["https://janesmith.com"]
}
```

All fields optional. Provide whatever public identifiers are available.

### Response

```json
{
  "profile": { ...CognitiveProfile }
}
```

---

## POST /ingest

Parses any consumption history and uses it to enrich the cognitive profile. Accepts raw pasted or exported content from any source — Claude conversation history, Pocket CSV, Kindle highlights, browser bookmarks, YouTube watch history, OPML, Twitter bookmarks, or freeform text.

Claude auto-detects the format if no hint is provided.

### Request

```json
{
  "content": "<raw pasted content>",
  "format": "claude",
  "extract_signals": true
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `content` | string | yes | Raw pasted or exported content. Up to ~80,000 characters (larger pastes are truncated). |
| `format` | string | no | Format hint for better parsing accuracy. See supported values below. Omit to auto-detect. |
| `extract_signals` | boolean | no | If `true` (default), extracts cognitive signals and merges into profile. Set `false` to only embed items into the vector store without touching the profile. |

**Supported `format` values**

| Value | Source |
|---|---|
| `claude` | Claude.ai conversation history — JSON export or copy-pasted conversation text |
| `pocket` | Pocket CSV export |
| `kindle` | Kindle highlights — My Clippings CSV or text export |
| `browser` | Browser bookmarks HTML (Chrome, Firefox, Safari) |
| `youtube` | Google Takeout `watch-history.json` |
| `opml` | OPML RSS/podcast subscription list |
| `twitter` | Twitter/X bookmarks JSON or copy-pasted threads |
| `raw` | Freeform text — URLs, titles, notes, anything |

### Response

```json
{
  "items_parsed": 47,
  "items_embedded": 47,
  "profile_changes": {
    "mental_models_added": ["counterfactual reasoning", "network externalities"],
    "third_order_added": ["mechanism inversion"],
    "interests_added": ["prediction markets", "mechanism design"]
  }
}
```

| Field | Type | Description |
|---|---|---|
| `items_parsed` | number | Number of distinct content items extracted from the paste |
| `items_embedded` | number | Number of items embedded into the vector store |
| `profile_changes` | object | Summary of what was added to the cognitive profile. Empty lists if `extract_signals` was false or nothing new was found. |

---

## POST /feedback

Processes voice or text feedback about a post and updates the cognitive profile. Extracts new exclusions, interests, tone updates, and mental model refinements. Appends to feedback history.

### Request

```json
{
  "transcript": "I felt like this post was too abstract — I want more concrete mechanisms. Also I never want to write about NFTs again.",
  "post_topic": "how token incentive structures mirror medieval guild economics"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `transcript` | string | yes | Raw feedback text or voice transcript |
| `post_topic` | string | no | The topic the feedback refers to, for context |

### Response

```json
{
  "changes": "Added 'NFTs' to exclusions. Updated tone preference toward more concrete mechanism-level analysis. No changes to mental models.",
  "updated_profile": { ...CognitiveProfile }
}
```

| Field | Type | Description |
|---|---|---|
| `changes` | string | Plain-English summary of what changed in the profile |
| `updated_profile` | CognitiveProfile | Full updated profile |

---

## GET /profile

Returns the current cognitive profile.

### Response

```json
{
  "version": 1,
  "last_updated": "2025-04-10T14:32:00Z",
  "topics": {
    "covered": ["how RLHF changes the implicit contract between model and annotator"],
    "interests": ["mechanism design", "prediction markets", "philosophy of science"],
    "exclusions": ["partisan politics", "NFTs"]
  },
  "mental_models": [
    {
      "model": "abstraction layer analysis",
      "description": "Breaks systems into levels, looks for where value is captured at each layer",
      "evidence": ["post: The Middleware Moment", "read: Stratechery - Aggregation Theory"]
    }
  ],
  "third_order": [
    {
      "pattern": "isomorphic systems",
      "description": "Finds topics compelling when two unrelated systems share the same underlying structure",
      "evidence": ["post: Guild Tokens"]
    }
  ],
  "tone_preferences": {
    "style": "synthesis-heavy, intellectually rigorous",
    "depth": "assumes domain familiarity, skips basics",
    "avoid": "listicles, surface takes, obvious conclusions"
  },
  "feedback_history": [
    {
      "timestamp": "2025-04-09T10:00:00Z",
      "post_topic": "guild economics",
      "transcript": "too abstract...",
      "changes_summary": "Updated tone toward concrete mechanisms"
    }
  ]
}
```

See [CognitiveProfile](#cognitiveprofile) for full type definition.

---

## PUT /profile

Merges a partial or full profile update. Use this for manual edits — adding exclusions, seeding interests, adjusting tone, editing mental models.

Feedback history is never overwritten via this endpoint.

### Request

Any partial subset of the CognitiveProfile schema. Only provided fields are updated.

```json
{
  "topics": {
    "interests": ["information theory", "institutional economics"],
    "exclusions": ["Web3", "NFTs"]
  },
  "tone_preferences": {
    "avoid": "listicles, rhetorical questions, obvious conclusions"
  }
}
```

### Response

Full updated `CognitiveProfile`.

---

## GET /topics

Returns the top 5 ranked topic candidates based on the current cognitive profile.

Candidates are scored by relevance to your mental models (Claude) and novelty relative to your existing content (vector store distance), then ranked with Maximal Marginal Relevance to ensure diversity.

### Query Parameters

| Param | Type | Default | Description |
|---|---|---|---|
| `refresh` | boolean | `false` | Force regeneration of candidates. Currently always regenerates — reserved for future caching. |

### Response

```json
{
  "top": {
    "topic": "why AI agent autonomy hits the same principal-agent ceiling as corporate middle management, and what that implies for which tasks agents will structurally fail at",
    "rationale": "Engages the writer's abstraction layer analysis and principal-agent mental models. The isomorphic systems pattern is strongly triggered by the structural parallel.",
    "mental_model_fit": "abstraction layer analysis, principal-agent theory",
    "third_order_fit": "isomorphic systems",
    "relevance_score": 0.87,
    "novelty_score": 0.73,
    "combined_score": 0.83
  },
  "candidates": [
    {
      "topic": "why AI agent autonomy hits the same principal-agent ceiling...",
      "rationale": "...",
      "mental_model_fit": "...",
      "third_order_fit": "...",
      "relevance_score": 0.87,
      "novelty_score": 0.73,
      "combined_score": 0.83,
      "mmr_score": 0.79
    },
    ...
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `top` | Candidate | The highest-ranked candidate |
| `candidates` | Candidate[] | All 5 ranked candidates with scores |

**Candidate fields**

| Field | Type | Description |
|---|---|---|
| `topic` | string | The specific topic string, framed at depth |
| `rationale` | string | Why this fits the cognitive profile |
| `mental_model_fit` | string | Which mental models from the profile this engages |
| `third_order_fit` | string | Which third-order patterns this satisfies |
| `relevance_score` | number 0–1 | Claude-scored fit against the cognitive profile |
| `novelty_score` | number 0–1 | Vector store distance from nearest existing content (higher = more novel) |
| `combined_score` | number 0–1 | Weighted combination: `relevance * 0.7 + novelty * 0.3` |
| `mmr_score` | number | MMR score after diversity penalty |

---

## POST /generate

Researches a topic using Claude with web search and writes a post in the user's voice at the depth specified by the cognitive profile.

This is a two-step Claude call: research first, then write. Expect 30–90 seconds.

### Request

```json
{
  "topic": "why AI agent autonomy hits the same principal-agent ceiling as corporate middle management"
}
```

### Response

```json
{
  "title": "The Management Layer You Can't Automate Away",
  "body_html": "<p>The failure mode of AI agents...</p>",
  "topic": "why AI agent autonomy hits the same principal-agent ceiling...",
  "sources": [
    {
      "title": "Principal-Agent Problems in AI Alignment",
      "url": "https://arxiv.org/abs/...",
      "key_claim": "Reward misspecification in RLHF mirrors classical principal-agent divergence",
      "surprising_angle": "The authors show that the problem worsens non-linearly with agent capability"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `title` | string | Post title — terse, not clickbait |
| `body_html` | string | Full post body as HTML. Only uses `<p>`, `<strong>`, `<em>`, `<a>`, `<blockquote>`. |
| `topic` | string | The topic as submitted |
| `sources` | Source[] | 5–8 sources found during research |

**Source fields**

| Field | Type | Description |
|---|---|---|
| `title` | string | Source title |
| `url` | string | Source URL |
| `key_claim` | string | Core finding or argument |
| `surprising_angle` | string | Non-obvious angle relevant to the post |

---

## POST /audio

Generates an audio overview of a post. Claude adapts the HTML into a narration script optimized for listening (same intellectual depth, no explainer opener), then ElevenLabs voices it to MP3.

Requires `ELEVENLABS_API_KEY`.

### Request

```json
{
  "title": "The Management Layer You Can't Automate Away",
  "body_html": "<p>The failure mode of AI agents...</p>"
}
```

### Response

```json
{
  "script": "The failure mode everyone keeps misattributing to technical limitations...\n\nThere's a structural reason that...",
  "audio_path": "data/audio/the-management-layer-you-cant-automate-away.mp3",
  "public_url": "https://cdn.example.com/audio/the-management-layer-you-cant-automate-away.mp3",
  "embed_html": "<p><audio controls style=\"width:100%\"><source src=\"https://...\" type=\"audio/mpeg\">Your browser doesn't support the audio element.</audio></p>"
}
```

| Field | Type | Description |
|---|---|---|
| `script` | string | The narration text (400–700 words) |
| `audio_path` | string | Local file path where the MP3 was saved |
| `public_url` | string \| null | Public URL for the audio file. Null if `AUDIO_PUBLIC_BASE_URL` is not configured. |
| `embed_html` | string \| null | Ready-to-use `<audio>` HTML element. Null if no public URL. Prepend this to `body_html` before publishing if you want the player in the post. |

### Errors

| Status | Condition |
|---|---|
| `501` | `ELEVENLABS_API_KEY` is not set |
| `500` | ElevenLabs API error or synthesis failure |

---

## POST /publish

Publishes a post to Substack via Playwright browser automation. Logs in if not authenticated, fills in title and body, and clicks publish.

Requires `SUBSTACK_URL`, `SUBSTACK_EMAIL`, `SUBSTACK_PASSWORD`.

### Request

```json
{
  "title": "The Management Layer You Can't Automate Away",
  "body_html": "<p>The failure mode of AI agents...</p>"
}
```

To include an audio player, prepend the `embed_html` from `POST /audio` to `body_html` before sending.

### Response

```json
{
  "url": "https://yourname.substack.com/p/the-management-layer-you-cant-automate"
}
```

### Errors

| Status | Condition |
|---|---|
| `500` | Login failed, editor not found, publish button not found, or post URL not returned |

---

## POST /run

Manually triggers the full end-to-end pipeline — the same job that runs on the cron schedule. Selects a topic, researches and writes the post, generates audio, publishes to Substack, marks the topic covered, and logs the run.

No request body.

### Response

```json
{
  "timestamp": "2025-04-10T15:00:00Z",
  "topic": "why AI agent autonomy hits the same principal-agent ceiling...",
  "post_url": "https://yourname.substack.com/p/the-management-layer",
  "audio_path": "data/audio/the-management-layer.mp3",
  "status": "success",
  "error": null
}
```

| Field | Type | Description |
|---|---|---|
| `timestamp` | string | ISO 8601 UTC timestamp |
| `topic` | string | Topic that was selected and written |
| `post_url` | string | Published post URL |
| `audio_path` | string \| null | Local path to generated MP3. Null if `ELEVENLABS_API_KEY` not set. |
| `status` | string | `"success"` or `"error"` |
| `error` | string \| null | Error message if status is `"error"` |

### Errors

| Status | Condition |
|---|---|
| `500` | Any step in the pipeline failed. Partial state may have been written (e.g. audio generated but publish failed). |

---

## Data Types

### CognitiveProfile

```typescript
{
  version: number                  // schema version, currently 1
  last_updated: string | null      // ISO 8601 UTC
  topics: {
    covered: string[]              // topics already written — never repeated
    interests: string[]            // seed domains to draw from
    exclusions: string[]           // hard blocks — never suggested or written
  }
  mental_models: MentalModel[]
  third_order: ThirdOrderPattern[]
  tone_preferences: {
    style: string                  // e.g. "synthesis-heavy, intellectually rigorous"
    depth: string                  // e.g. "assumes domain familiarity, skips basics"
    avoid: string                  // e.g. "listicles, surface takes"
  }
  feedback_history: FeedbackEntry[]
}
```

### MentalModel

```typescript
{
  model: string         // short name, e.g. "abstraction layer analysis"
  description: string   // what the model is and how this writer uses it
  evidence: string[]    // specific titles, prefixed "post:" or "read:"
}
```

### ThirdOrderPattern

```typescript
{
  pattern: string       // short name, e.g. "isomorphic systems"
  description: string   // what type of insight the user seeks
  evidence: string[]    // specific titles as evidence
}
```

### FeedbackEntry

```typescript
{
  timestamp: string     // ISO 8601 UTC
  post_topic: string | null
  transcript: string    // original feedback text
  changes_summary: string  // what changed as a result
}
```

---

## Error Responses

All error responses use standard HTTP status codes with a JSON body:

```json
{
  "detail": "Human-readable error message"
}
```

| Status | Meaning |
|---|---|
| `422` | Request body validation failed — check required fields and types |
| `500` | Internal server error — check server logs |
| `501` | Feature not configured — a required API key (ElevenLabs, Perplexity) is missing |
