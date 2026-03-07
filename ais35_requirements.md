# AIS-35: Conversation History Summarization - Detailed Requirements

## Problem Statement

Long chat conversations exceed model context windows, causing:
1. **Token limit errors** - Chat fails when history too large
2. **Lost context** - Older messages dropped entirely, losing important context
3. **Poor search** - No way to find relevant chats by topic/keywords
4. **No continuity** - Agent can't reference previous discussions across sessions

**Goal**: Implement conversation summarization "like Copilot" to:
- Compress old messages while preserving key information
- Keep conversations within token budgets
- Enable searching past chats by topic
- Support project/task-scoped chat history review

---

## Current State Analysis

### Existing Infrastructure ✅

**1. Chat System** (`backend/app/models/chat.py`):
- `ChatSession` - Stores session metadata (title, models, agent, project_slug, task_id)
- `ChatMessage` - Individual messages with role (user/assistant/system)
- `protocol_state` field - JSON for todo lists, delegation state
- `unread_count` - Tracks unread messages
- Auto-title - Generates short title from first messages

**2. History Building** (`backend/app/api/chat.py:1088`):
```python
# Current: Load ALL messages every time
for msg in session.messages:
    if msg.role != "system":
        history.append({"role": msg.role, "content": msg.content})
```
**Problem**: No truncation, no summarization, all messages sent to LLM.

**3. Existing Summarization Hooks**:
- `text_summarize` skill exists (stub, not implemented)
- `cycle_summary` in autonomous runs (summarizes previous cycle results)
- Auto-title feature (summarizes first messages to 3-6 words)
- Memory system has "summary" type (ChromaDB for long-term facts)

**4. Token Tracking**:
- Messages have `total_tokens`, `prompt_tokens`, `completion_tokens`
- Generation params have `num_ctx` (32768 default context window)
- No token budget management in chat API

**5. Search Capabilities**:
- No chat search by content/topic
- Can filter by `chat_type`, `project_slug`, `task_id`
- Memory search exists (ChromaDB vectors) but not for chat history

---

## VS Code Copilot Reference

How GitHub Copilot Chat handles long conversations:

### Token Budget Management
1. **Context Window**: ~32K tokens (model dependent)
2. **Budget Allocation**:
   - System prompt: ~2-4K tokens
   - Recent messages: ~20K tokens (full content)
   - Summary of older messages: ~4-6K tokens (compressed)
   - Response buffer: ~6K tokens reserved

### Summarization Strategy
1. **Trigger**: When prompt + history > 75% of context window
2. **Window**: Keep last 10-15 messages verbatim
3. **Summary**: Compress everything before the window into 1 summary message
4. **Progressive**: If summary itself too large, summarize the summary (recursive)

### Summary Content
- Key topics discussed
- Important decisions/conclusions
- Code snippets referenced (file paths, function names)
- Unresolved questions
- Action items / TODOs

### Implementation
- Summary appears as special `system` message at start of history
- Format: "**Previous conversation summary:** [summary text]"
- User sees indicator: "✨ Using summarized history (45 messages compressed)"

---

## Proposed Solution

### Core Features (MVP)

#### 1. **Conversation Summarization Protocol**

**Database Schema Changes:**
```python
# Add to ChatSession model
summary: Mapped[str | None] = mapped_column(Text, nullable=True)
summary_up_to_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID, nullable=True)
summary_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
summary_token_count: Mapped[int] = mapped_column(Integer, default=0)
```

**Summary Storage Options:**
- **Option A**: Store in `ChatSession.summary` (single rolling summary)
- **Option B**: Create `ChatSummary` table (multiple summaries per session for progressive compression)
- **Recommendation**: Start with Option A (simpler), migrate to B if needed

**Summary Metadata:**
- Which message was last included in summary
- When summary was created
- Token count of summary
- Summary version (for progressive summarization)

#### 2. **Auto-Summarization Logic**

**Trigger Conditions** (any of):
1. Total history tokens > 75% of `num_ctx`
2. Message count > 50
3. Manual user request
4. Session inactive > 1 day (background job)

**Algorithm**:
```python
async def check_and_summarize(session: ChatSession, db: AsyncSession):
    """Check if summarization needed and trigger if so."""
    # Calculate current token usage
    total_tokens = sum(estimate_tokens(m.content) for m in session.messages)
    context_limit = get_session_context_limit(session)  # from agent settings or default
    
    if total_tokens > context_limit * 0.75:
        await create_summary(session, db)
```

**Summary Window**:
- Keep last N messages verbatim (N = 15 default, configurable per agent)
- Summarize all messages before the window
- Update `summary_up_to_message_id` to track boundary

**Summary Prompt**:
```
Summarize the following conversation history concisely but comprehensively:

1. Key topics and questions discussed
2. Important decisions or conclusions reached
3. Code, files, or systems mentioned (with paths/names)
4. Unresolved questions or pending items
5. Context needed for future messages

Conversation to summarize:
[messages 1 to N-15]

Provide a summary in 200-500 words that captures all essential context.
```

#### 3. **History Building with Summary**

**Modified `send_message` flow**:
```python
# Build conversation history
history = []
if system_prompt:
    history.append({"role": "system", "content": system_prompt})

# If session has summary, inject it
if session.summary and session.summary_up_to_message_id:
    summary_text = f"**Previous conversation summary** (up to message {session.summary_up_to_message_id}):\n\n{session.summary}"
    history.append({"role": "system", "content": summary_text})
    
    # Only include messages AFTER the summarized portion
    recent_messages = [m for m in session.messages if m.id > session.summary_up_to_message_id]
else:
    recent_messages = session.messages

for msg in recent_messages:
    if msg.role != "system":
        history.append({"role": msg.role, "content": msg.content})
```

**Token Estimation**:
```python
def estimate_tokens(text: str) -> int:
    """Rough estimate: 1 token ≈ 4 characters."""
    return len(text) // 4
```
(Can be improved with tiktoken or similar, but rough estimate sufficient for MVP)

#### 4. **User Interface Indicators**

**Frontend (`ChatPanel.vue`):**
- Show indicator when summary active: "✨ 45 messages summarized"
- Button to view/regenerate summary
- Option to "expand full history" (load all messages, may hit token limit)

**API Response:**
```python
class ChatSessionResponse(BaseModel):
    # ... existing fields ...
    has_summary: bool = False
    summary_message_count: int = 0  # how many messages compressed
    summary_preview: str | None = None  # first 100 chars
```

#### 5. **Search Past Chats by Topic**

**Use Case**: "Show me all chats where we discussed authentication"

**Implementation Options:**

**Option A: Simple SQL LIKE search** (MVP)
```python
@router.get("/chat/search")
async def search_chats(
    query: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search chat sessions and messages by content."""
    # Search in session titles
    sessions = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .where(ChatSession.title.ilike(f"%{query}%"))
    )
    # Search in message content
    messages = await db.execute(
        select(ChatMessage)
        .join(ChatSession)
        .where(ChatSession.user_id == user.id)
        .where(ChatMessage.content.ilike(f"%{query}%"))
    )
    # Also search in summaries
    summary_sessions = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .where(ChatSession.summary.ilike(f"%{query}%"))
    )
```

**Option B: Vector search** (Future enhancement)
- Store message embeddings in ChromaDB
- Semantic search instead of keyword search
- More accurate, handles synonyms

**Option C: LLM-powered search** (Future)
- Ask LLM: "Find chats about authentication"
- LLM queries ChromaDB or generates SQL

**Recommendation**: Start with Option A (simple, works), add Option B later

#### 6. **Project/Task Chat History Review**

**Use Case**: Agent working on task T-5 needs to see all related chats

**Implementation**:
```python
@router.get("/chat/sessions/by-project/{project_slug}")
async def get_project_chats(
    project_slug: str,
    task_id: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all chats related to a project or specific task."""
    query = select(ChatSession).where(
        ChatSession.user_id == user.id,
        ChatSession.project_slug == project_slug,
    )
    if task_id:
        query = query.where(ChatSession.task_id == task_id)
    
    result = await db.execute(query.order_by(ChatSession.updated_at.desc()))
    sessions = result.scalars().all()
    
    # Return with summaries for quick scanning
    return {
        "project_slug": project_slug,
        "task_id": task_id,
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "summary": s.summary[:200] if s.summary else None,
                "message_count": len(s.messages),
                "created_at": s.created_at,
            }
            for s in sessions
        ]
    }
```

**Frontend Integration**:
- Add "Related Chats" panel in project view
- Show chat summaries for quick scanning
- Click to open full chat session

---

## Implementation Plan

### Phase 1: Core Summarization (MVP)

**Backend:**
1. Add summary fields to `ChatSession` model (migration)
2. Implement `estimate_tokens()` function
3. Implement `create_summary()` function (uses LLM)
4. Add auto-summarization check in `send_message`
5. Modify history building to inject summary

**Frontend:**
1. Show summary indicator in ChatPanel
2. Add "View Summary" button
3. Display summary in expandable section

**Testing:**
1. Create chat with 100+ messages
2. Verify auto-summarization triggers
3. Verify summary appears in context
4. Verify token usage reduced

### Phase 2: Search & Discovery

**Backend:**
1. Add `/chat/search` endpoint (keyword search)
2. Add `/chat/sessions/by-project/{slug}` endpoint
3. Add search to summaries

**Frontend:**
1. Add search bar in ChatPanel
2. Show search results with highlights
3. Add "Related Chats" panel in project view

### Phase 3: Progressive Summarization (Future)

**Backend:**
1. Create `ChatSummary` table for multiple summaries
2. Implement recursive summarization (summary of summaries)
3. Add version tracking

### Phase 4: Advanced Features (Future)

1. **Manual summary editing** - Let user refine LLM-generated summary
2. **Summary templates** - Different summary styles (technical, executive, code-focused)
3. **Export summaries** - Download as markdown/PDF
4. **Vector search** - Semantic search with embeddings
5. **Summary-based context injection** - Automatically load relevant past conversations

---

## Technical Decisions

### 1. Where to Store Summaries?

**Option A: In `ChatSession.summary` field**
- ✅ Simple, no new tables
- ✅ Fast access (loaded with session)
- ❌ Only one summary per session (need to replace when growing)
- ❌ Can't track summary history/versions

**Option B: New `ChatSummary` table**
- ✅ Multiple summaries per session (progressive compression)
- ✅ Track summary history/versions
- ❌ More complex queries
- ❌ Extra JOIN on every chat load

**Decision**: Start with Option A, migrate to B if needed.

### 2. When to Trigger Summarization?

**Option A: On every message (if threshold exceeded)**
- ✅ Always up-to-date
- ❌ Adds latency to chat
- ❌ Extra LLM calls

**Option B: Background job**
- ✅ No user-facing latency
- ❌ Summary might be stale
- ❌ Requires job scheduler

**Option C: On-demand (when loading history)**
- ✅ Only when needed
- ❌ First message after threshold hits expensive

**Decision**: Start with Option A (simpler), move to B for better UX.

### 3. How Many Messages to Keep Verbatim?

**Factors**:
- Recent messages most relevant (recency bias)
- Longer window = more context, but more tokens
- Agent protocols need recent protocol state (todo list, delegation)

**Decision**: 15 messages default, configurable per agent (5-30 range).

### 4. Summary Token Budget?

**Analysis**:
- Default context: 32K tokens
- System prompt: ~2-4K
- Summary target: ~3-5K (500-800 words)
- Recent messages: ~15-20K
- Response buffer: ~5K

**Decision**: Aim for 500-word summaries (~3K tokens). If summary > 5K tokens, trigger recursive summarization.

---

## Success Criteria

### MVP (Phase 1):
- ✅ Chats with 100+ messages automatically summarize
- ✅ Token usage stays under context limit
- ✅ Summary preserves key context (verified by manual testing)
- ✅ UI shows summary indicator
- ✅ No user-facing errors due to token limits

### Phase 2:
- ✅ User can search chats by keyword
- ✅ Search includes summaries
- ✅ Project view shows related chats

### Phase 3+:
- ✅ Progressive summarization for very long chats (500+ messages)
- ✅ Vector search for semantic queries

---

## Open Questions

1. **Summary model**: Use same model as chat or separate (faster/cheaper) model?
   - Recommendation: Use same model initially, optimize later

2. **Summary style**: Bullet points or prose?
   - Recommendation: Structured format with sections (topics, decisions, code, questions)

3. **User control**: Can user manually trigger summary or edit it?
   - Recommendation: Start auto-only, add manual later

4. **Multi-agent summaries**: How to handle multi-agent conversations?
   - Recommendation: Include agent names in summary, preserve delegation context

5. **Autonomous runs**: Should autonomous cycle summaries persist in chat?
   - Recommendation: Yes, link autonomous runs to chat sessions

6. **Summary caching**: Cache summaries in Redis?
   - Recommendation: No for MVP (stored in DB is sufficient)

---

## Related Systems

### Integration Points:

1. **Agent Protocols** (`protocol_executor.py`):
   - Summary should preserve protocol state (active child, delegation stack)
   - Include todo list snapshot in summary

2. **Autonomous Runs** (`autonomous_runner.py`):
   - Already has `cycle_summary` concept
   - Link autonomous chat sessions to main agent chat
   - Include cycle summaries in overall chat summary

3. **Memory System** (`memory.py`):
   - Chat summaries can feed into long-term memory (ChromaDB)
   - Store important facts/decisions as memory entries
   - Use memory search for cross-session context

4. **Project Context** (AIS-34):
   - Chat summaries enhance project context
   - When building project context, include relevant chat summaries
   - "Show me all chats about this project" feature

5. **Thinking Logs** (`thinking_log.py`):
   - Thinking steps already tracked per message
   - Include thinking summary in chat summary?
   - Or keep separate (thinking = debug, summary = context)

---

## Implementation Notes

### Token Estimation

For MVP, use simple heuristic:
```python
def estimate_tokens(text: str) -> int:
    """Rough estimate: 1 token ≈ 4 characters."""
    return len(text) // 4
```

For production, consider:
- `tiktoken` library (OpenAI tokenizer)
- Model-specific tokenizers
- Cache token counts per message (add `token_count` field to `ChatMessage`)

### Summary Quality

Test summary quality by:
1. Manual review of summaries
2. Agent performance: Can agent answer questions using summary vs full history?
3. Token reduction: Target 70-80% reduction for summarized portion

### Error Handling

If summarization fails:
- Fallback: Keep recent messages, drop old ones entirely
- Log error for investigation
- Don't block chat flow

---

## Example Summary

**Input**: 50 messages discussing building authentication system

**Output**:
```
**Previous Conversation Summary** (messages 1-35):

**Topics Discussed:**
- Designed JWT-based authentication system with access/refresh tokens
- Chose bcrypt for password hashing (12 rounds)
- Decided on Redis for token blacklist storage

**Key Decisions:**
- Access token: 15 min expiry
- Refresh token: 7 days expiry
- Endpoint: POST /api/auth/login, /api/auth/refresh
- Password requirements: 8 chars, 1 uppercase, 1 number

**Code/Files Referenced:**
- backend/app/api/auth.py - Login endpoint implementation
- backend/app/core/security.py - JWT functions
- backend/app/models/user.py - User model with hashed_password field

**Unresolved Questions:**
- Should we add 2FA support? (Deferred to phase 2)
- Rate limiting strategy for login attempts?

**Action Items:**
- Add password reset flow
- Write tests for token refresh
- Document API in OpenAPI schema
```

---

## Conclusion

AIS-35 requires:

1. **Database changes**: Add summary fields to ChatSession
2. **Core logic**: Token estimation + auto-summarization
3. **History building**: Inject summary, load recent messages only
4. **UI updates**: Show summary indicator, search interface
5. **API endpoints**: Search, project chat history

**Priority**: HIGH (prevents token limit errors in production)
**Complexity**: MEDIUM (mostly backend, some frontend work)
**Dependencies**: None (standalone feature)
**Risk**: LOW (graceful fallback if summarization fails)
