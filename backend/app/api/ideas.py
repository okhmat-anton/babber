"""
Ideas API.

Global and per-agent ideas management.

Endpoints:
  GET    /api/ideas                          — list all ideas (global view)
  POST   /api/ideas                          — create an idea
  POST   /api/ideas/suggest                  — AI-generate idea suggestions
  GET    /api/ideas/{id}                     — get a single idea
  PATCH  /api/ideas/{id}                     — update an idea
  DELETE /api/ideas/{id}                     — delete an idea
  GET    /api/agents/{agent_id}/ideas        — list ideas for an agent
  POST   /api/agents/{agent_id}/ideas        — create an idea for an agent
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.services import IdeaService, AgentService
from app.mongodb.models.idea import MongoIdea

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ideas"])

VALID_STATUSES = {"new", "in_progress", "done", "archived"}
VALID_PRIORITIES = {"low", "medium", "high"}
VALID_SOURCES = {"user", "agent"}


# ── Schemas ──────────────────────────────────────────

class IdeaCreate(BaseModel):
    title: str
    description: str = ""
    source: str = "user"
    category: Optional[str] = None
    priority: str = "medium"
    status: str = "new"
    tags: List[str] = []


class IdeaUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None


class SuggestIdeasRequest(BaseModel):
    agent_id: str
    topic: str = ""
    context_types: List[str] = []  # ideas, notes, facts, beliefs, aspirations, events, videos, projects, tasks, analysis, resources
    akm_context_types: List[str] = []  # issues, epics, sprints
    urls: List[str] = []  # URLs to fetch and include as context


# ── Helpers ──────────────────────────────────────────

def _idea_to_response(idea: MongoIdea) -> dict:
    return {
        "id": idea.id,
        "title": idea.title,
        "description": idea.description,
        "source": idea.source,
        "agent_id": idea.agent_id,
        "category": idea.category,
        "priority": idea.priority,
        "status": idea.status,
        "tags": idea.tags,
        "linked_video_ids": getattr(idea, 'linked_video_ids', []) or [],
        "linked_fact_ids": getattr(idea, 'linked_fact_ids', []) or [],
        "linked_analysis_ids": getattr(idea, 'linked_analysis_ids', []) or [],
        "created_by": idea.created_by,
        "created_at": idea.created_at.isoformat() if isinstance(idea.created_at, datetime) else str(idea.created_at),
        "updated_at": idea.updated_at.isoformat() if isinstance(idea.updated_at, datetime) else str(idea.updated_at),
    }


# ── Global Endpoints ─────────────────────────────────

@router.get("/api/ideas")
async def list_all_ideas(
    status: Optional[str] = Query(None, description="Filter by status: new, in_progress, done, archived"),
    source: Optional[str] = Query(None, description="Filter by source: user or agent"),
    agent_id: Optional[str] = Query(None, description="Filter by agent"),
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Text search in title/description"),
    limit: int = Query(200, ge=1, le=500),
    skip: int = Query(0, ge=0),
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List all ideas (global view)."""
    svc = IdeaService(db)
    items = await svc.get_all_ideas(
        status=status, source=source, agent_id=agent_id,
        category=category, search=search, limit=limit, skip=skip,
    )
    return {"items": [_idea_to_response(i) for i in items], "total": len(items)}


@router.post("/api/ideas", status_code=201)
async def create_idea(
    body: IdeaCreate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Create an idea (global, no agent)."""
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(VALID_STATUSES)}")
    if body.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority must be one of: {', '.join(VALID_PRIORITIES)}")
    if body.source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail=f"source must be one of: {', '.join(VALID_SOURCES)}")

    idea = MongoIdea(
        title=body.title.strip(),
        description=body.description.strip() if body.description else "",
        source=body.source,
        agent_id=None,
        category=body.category,
        priority=body.priority,
        status=body.status,
        tags=body.tags,
        created_by=body.source,
    )
    svc = IdeaService(db)
    created = await svc.create(idea)
    return _idea_to_response(created)


# ── Suggest Ideas (AI generation) ────────────────────

@router.post("/api/ideas/suggest")
async def suggest_ideas(
    body: SuggestIdeasRequest,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Use an agent's LLM to generate 5-10 new idea suggestions based on system context."""
    import httpx
    import re as _re
    from app.api.chat import _resolve_model, _chat_with_model
    from app.api.agent_files import read_agent_config, read_agent_settings
    from app.api.agent_beliefs import read_beliefs
    from app.api.agent_aspirations import read_aspirations
    from app.api.settings import get_setting_value
    from app.llm.base import GenerationParams, Message
    from app.mongodb.services import (
        AgentFactService, NoteService, AgentService,
        WatchedVideoService, AnalysisTopicService, ResearchResourceService,
    )
    from app.mongodb.task_service import list_tasks
    from app.config import get_settings
    from pathlib import Path

    # Validate agent
    agent_svc = AgentService(db)
    agent = await agent_svc.get_by_id(body.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Resolve model for this agent
    agent_config = read_agent_config(agent.name)
    agent_settings = read_agent_settings(agent.name)

    # Get agent's primary model
    from app.mongodb.services import AgentModelService
    agent_model_svc = AgentModelService(db)
    agent_models = await agent_model_svc.get_all(filter={"agent_id": body.agent_id}, limit=10)
    if not agent_models:
        raise HTTPException(status_code=400, detail="Agent has no models assigned")

    model_id = str(agent_models[0].model_config_id)
    provider, base_url, model_name, api_key = await _resolve_model(model_id, db)

    # Build context sections
    context_parts = []

    # 1. Load existing ideas (always — to avoid duplicates)
    idea_svc = IdeaService(db)
    all_ideas = await idea_svc.get_all_ideas(limit=200)
    existing_titles = [i.title for i in all_ideas]
    if all_ideas and "ideas" in body.context_types:
        ideas_text = "\n".join(
            f"- {i.title}" + (f": {i.description[:200]}" if i.description else "")
            for i in all_ideas[:100]
        )
        context_parts.append(f"## Existing Ideas in System\n{ideas_text}")

    # 2. Notes
    if "notes" in body.context_types:
        note_svc = NoteService(db)
        notes = await note_svc.get_all_notes(status="active", limit=100)
        if notes:
            notes_text = "\n".join(
                f"- {n.title}" + (f": {n.content[:200]}" if n.content else "")
                for n in notes
            )
            context_parts.append(f"## User Notes\n{notes_text}")

    # 3. Facts (agent-specific)
    if "facts" in body.context_types:
        fact_svc = AgentFactService(db)
        facts = await fact_svc.get_by_agent(body.agent_id, limit=100)
        if facts:
            facts_text = "\n".join(f"- [{f.type}] {f.content[:200]}" for f in facts)
            context_parts.append(f"## Agent Facts & Hypotheses\n{facts_text}")

    # 4. Beliefs
    if "beliefs" in body.context_types:
        beliefs = read_beliefs(agent.name)
        if beliefs.get("core") or beliefs.get("additional"):
            beliefs_items = beliefs.get("core", []) + beliefs.get("additional", [])
            beliefs_text = "\n".join(
                f"- {b}" if isinstance(b, str) else f"- {b.get('text', str(b))}"
                for b in beliefs_items
            )
            context_parts.append(f"## Agent Beliefs\n{beliefs_text}")

    # 5. Aspirations
    if "aspirations" in body.context_types:
        aspirations = read_aspirations(agent.name)
        asp_parts = []
        for asp_type in ["dreams", "desires", "goals"]:
            items = aspirations.get(asp_type, [])
            if items:
                for item in items:
                    text = item.get("text", str(item)) if isinstance(item, dict) else str(item)
                    asp_parts.append(f"- [{asp_type}] {text}")
        if asp_parts:
            context_parts.append(f"## Agent Aspirations\n" + "\n".join(asp_parts))

    # 6. Events (agent-specific)
    if "events" in body.context_types:
        from app.mongodb.services import AgentEventService
        event_svc = AgentEventService(db)
        events_cursor = event_svc.collection.find(
            {"agent_id": body.agent_id}
        ).sort("created_at", -1).limit(50)
        events = await events_cursor.to_list(length=50)
        if events:
            events_text = "\n".join(
                f"- [{e.get('event_type', 'event')}] {e.get('title', '')}: {e.get('description', '')[:150]}"
                for e in events
            )
            context_parts.append(f"## Recent Agent Events\n{events_text}")

    # 7. Video transcriptions
    if "videos" in body.context_types:
        video_svc = WatchedVideoService(db)
        videos = await video_svc.get_all(limit=50)
        if videos:
            video_parts = []
            for v in videos:
                title = v.title or v.url
                transcript_preview = ""
                if v.transcript:
                    transcript_preview = f": {v.transcript[:300]}"
                video_parts.append(f"- [{v.platform}] {title}{transcript_preview}")
            context_parts.append(f"## Video Transcriptions\n" + "\n".join(video_parts))

    # 8. Projects
    if "projects" in body.context_types:
        app_settings = get_settings()
        projects_dir = Path(app_settings.PROJECTS_DIR)
        if projects_dir.exists():
            proj_parts = []
            for entry in sorted(projects_dir.iterdir(), key=lambda e: e.name.lower()):
                pjson = entry / "project.json"
                if entry.is_dir() and pjson.exists():
                    try:
                        pdata = json.loads(pjson.read_text(encoding="utf-8"))
                        name = pdata.get("name", entry.name)
                        desc = pdata.get("description", "")[:200]
                        status = pdata.get("status", "active")
                        proj_parts.append(f"- [{status}] {name}" + (f": {desc}" if desc else ""))
                    except Exception:
                        pass
            if proj_parts:
                context_parts.append(f"## Projects\n" + "\n".join(proj_parts))

    # 9. Tasks
    if "tasks" in body.context_types:
        tasks = await list_tasks(limit=100)
        if tasks:
            task_parts = []
            for t in tasks:
                agent_label = ""
                if t.agent_id:
                    a = await agent_svc.get_by_id(t.agent_id)
                    agent_label = f" @{a.name}" if a else ""
                task_parts.append(
                    f"- [{t.status}/{t.priority}] {t.title}{agent_label}"
                    + (f": {t.description[:150]}" if t.description else "")
                )
            context_parts.append(f"## Tasks\n" + "\n".join(task_parts))

    # 10. Analysis topics
    if "analysis" in body.context_types:
        analysis_svc = AnalysisTopicService(db)
        topics = await analysis_svc.get_global(limit=100)
        if topics:
            analysis_parts = []
            for t in topics:
                analysis_parts.append(
                    f"- [{t.status}] {t.title}"
                    + (f": {t.description[:200]}" if t.description else "")
                )
            context_parts.append(f"## Analysis Topics\n" + "\n".join(analysis_parts))

    # 11. Research resources (trusted)
    if "resources" in body.context_types:
        res_svc = ResearchResourceService(db)
        resources = await res_svc.get_all(limit=100)
        if resources:
            res_parts = []
            for r in resources:
                if getattr(r, "is_active", True):
                    res_parts.append(
                        f"- [{r.trust_level}] {r.name} ({r.url})"
                        + (f": {r.description[:150]}" if r.description else "")
                    )
            if res_parts:
                context_parts.append(f"## Trusted Research Resources\n" + "\n".join(res_parts))

    # 12. AKM Advisor context
    if body.akm_context_types:
        akm_key = await get_setting_value(db, "akm_advisor_api_key")
        akm_url = (await get_setting_value(db, "akm_advisor_url") or "").rstrip("/")
        if akm_key and akm_url:
            agent_headers = {"X-Agent-Key": akm_key}
            # Derive base URL for data API (leads/deals)
            parsed = urlparse(akm_url)
            akm_base = f"{parsed.scheme}://{parsed.netloc}"
            data_headers = {"Authorization": f"Bearer {akm_key}"}
            akm_parts = []
            try:
                async with httpx.AsyncClient(timeout=15, verify=False) as client:
                    # AKM project context
                    if "projects" in body.akm_context_types:
                        try:
                            r = await client.get(f"{akm_url}/context", headers=agent_headers)
                            if r.status_code == 200:
                                ctx = r.json()
                                akm_parts.append(
                                    f"### Project\n"
                                    f"Project: {ctx.get('name', '?')} ({ctx.get('key', '?')})\n"
                                    f"Description: {ctx.get('description', 'N/A')}\n"
                                    f"Issues: {ctx.get('total_issues', 0)} total, "
                                    f"{ctx.get('open_issues', 0)} open, "
                                    f"{ctx.get('in_progress_issues', 0)} in progress\n"
                                    f"Team: {', '.join(m.get('name', '?') for m in ctx.get('team_members', []))}"
                                )
                        except Exception:
                            pass

                    # AKM issues
                    if "issues" in body.akm_context_types:
                        try:
                            r = await client.get(
                                f"{akm_url}/issues",
                                headers=agent_headers,
                                params={"include_done": "false", "limit": 50},
                            )
                            if r.status_code == 200:
                                issues = r.json().get("items", [])
                                if issues:
                                    issues_text = "\n".join(
                                        f"- [{i.get('status')}/{i.get('priority')}] {i.get('key')}: {i.get('summary')}"
                                        for i in issues
                                    )
                                    akm_parts.append(f"### Open Issues\n{issues_text}")
                        except Exception:
                            pass

                    # AKM epics
                    if "epics" in body.akm_context_types:
                        try:
                            r = await client.get(f"{akm_url}/epics", headers=agent_headers)
                            if r.status_code == 200:
                                epics = r.json().get("items", [])
                                if epics:
                                    epics_text = "\n".join(
                                        f"- [{e.get('status')}] {e.get('key')}: {e.get('summary')} "
                                        f"({e.get('completed_issues', 0)}/{e.get('total_issues', 0)} done)"
                                        for e in epics
                                    )
                                    akm_parts.append(f"### Epics\n{epics_text}")
                        except Exception:
                            pass

                    # AKM sprints
                    if "sprints" in body.akm_context_types:
                        try:
                            r = await client.get(
                                f"{akm_url}/sprints",
                                headers=agent_headers,
                                params={"active_only": "true"},
                            )
                            if r.status_code == 200:
                                sprints = r.json().get("items", [])
                                if sprints:
                                    sprints_text = "\n".join(
                                        f"- [{s.get('status')}] {s.get('name')}: {s.get('goal', 'N/A')} "
                                        f"({s.get('completed_points', 0)}/{s.get('total_points', 0)} pts)"
                                        for s in sprints
                                    )
                                    akm_parts.append(f"### Active Sprints\n{sprints_text}")
                        except Exception:
                            pass

                    # AKM leads pipeline
                    if "leads" in body.akm_context_types:
                        try:
                            r = await client.get(
                                f"{akm_base}/api/v1/data/leads",
                                headers=data_headers,
                                params={"limit": 50, "page": 1},
                            )
                            if r.status_code == 200:
                                data = r.json()
                                items = data.get("items", data) if isinstance(data, dict) else data
                                if items:
                                    leads_text = "\n".join(
                                        f"- {ld.get('name', ld.get('title', 'N/A'))} "
                                        f"[{ld.get('status', '?')}] "
                                        f"{ld.get('company', ld.get('email', ''))}"
                                        for ld in (items if isinstance(items, list) else [])[:50]
                                    )
                                    akm_parts.append(
                                        f"### Leads Pipeline ({data.get('total', len(items))} total)\n{leads_text}"
                                    )
                        except Exception:
                            pass

                    # AKM deals pipeline
                    if "deals" in body.akm_context_types:
                        try:
                            r = await client.get(
                                f"{akm_base}/api/v1/data/deals",
                                headers=data_headers,
                                params={"limit": 50, "page": 1},
                            )
                            if r.status_code == 200:
                                data = r.json()
                                items = data.get("items", data) if isinstance(data, dict) else data
                                if items:
                                    deals_text = "\n".join(
                                        f"- {dl.get('name', dl.get('title', 'N/A'))} "
                                        f"[{dl.get('status', '?')}] "
                                        f"{dl.get('amount', '')} {dl.get('currency', '')}".strip()
                                        for dl in (items if isinstance(items, list) else [])[:50]
                                    )
                                    akm_parts.append(
                                        f"### Deals Pipeline ({data.get('total', len(items))} total)\n{deals_text}"
                                    )
                        except Exception:
                            pass

            except Exception as e:
                logger.warning("AKM Advisor context fetch failed: %s", e)

            if akm_parts:
                context_parts.append(f"## AKM Advisor (Project Management)\n" + "\n\n".join(akm_parts))

    # 13. Fetch URLs
    if body.urls:
        url_parts = []
        for url in body.urls[:10]:  # Max 10 URLs
            url = url.strip()
            if not url:
                continue
            try:
                async with httpx.AsyncClient(timeout=15, follow_redirects=True, verify=False) as client:
                    r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                    html = r.text
                    # Strip scripts/styles
                    html = _re.sub(r'<script[^>]*>.*?</script>', '', html, flags=_re.DOTALL)
                    html = _re.sub(r'<style[^>]*>.*?</style>', '', html, flags=_re.DOTALL)
                    # Extract text
                    text = _re.sub(r'<[^>]+>', ' ', html)
                    text = _re.sub(r'\s+', ' ', text).strip()[:3000]
                    if text:
                        url_parts.append(f"### {url}\n{text}")
            except Exception as e:
                url_parts.append(f"### {url}\nFailed to fetch: {e}")
        if url_parts:
            context_parts.append(f"## Fetched Web Pages\n\n" + "\n\n".join(url_parts))

    # Build the prompt
    context_block = "\n\n".join(context_parts) if context_parts else "No additional context provided."

    existing_titles_block = "\n".join(f"- {t}" for t in existing_titles) if existing_titles else "None yet."

    topic_instruction = ""
    if body.topic.strip():
        topic_instruction = f"\n\nThe user wants ideas specifically about: **{body.topic.strip()}**"

    system_prompt = agent_config.get("system_prompt", "You are a creative assistant.")

    user_prompt = f"""Based on the context provided below, generate between 5 and 10 new, unique, creative ideas.
{topic_instruction}

## Rules:
1. Each idea must be NEW — do NOT repeat ideas that already exist in the system (listed below).
2. Ideas should be practical, actionable, and relevant to the context.
3. For each idea provide a title and a brief description (2-3 sentences).
4. Assign a category and priority (low/medium/high) to each idea.
5. Return ONLY a valid JSON array with no extra text / markdown.

## Already existing ideas (DO NOT duplicate):
{existing_titles_block}

## System Context:
{context_block}

## Response Format:
Return a JSON array like this:
[
  {{"title": "Idea title", "description": "Brief description", "category": "Category name", "priority": "medium"}},
  ...
]

Generate 5-10 unique ideas now:"""

    gen_params = GenerationParams(
        temperature=0.9,
        top_p=0.95,
        max_tokens=8192,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = await _chat_with_model(provider, base_url, model_name, api_key, messages, gen_params)
        content = response.content.strip()

        # Try to extract JSON from the response
        # Remove markdown code fences if present
        if content.startswith("```"):
            # Find opening fence end and closing fence
            first_newline = content.index("\n")
            last_fence = content.rfind("```")
            if last_fence > first_newline:
                content = content[first_newline + 1:last_fence].strip()

        suggestions = json.loads(content)
        if not isinstance(suggestions, list):
            raise ValueError("Expected a JSON array")

        # Validate and normalize
        result = []
        for s in suggestions:
            if not isinstance(s, dict) or "title" not in s:
                continue
            result.append({
                "title": s["title"],
                "description": s.get("description", ""),
                "category": s.get("category", ""),
                "priority": s.get("priority", "medium") if s.get("priority") in ("low", "medium", "high") else "medium",
            })

        return {"suggestions": result, "count": len(result)}

    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM response as JSON: %s", response.content[:500] if 'response' in dir() else 'no response')
        raise HTTPException(status_code=500, detail="LLM returned invalid JSON. Try again.")
    except Exception as e:
        logger.error("Suggest ideas failed: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate ideas: {str(e)}")


@router.get("/api/ideas/{idea_id}")
async def get_idea(
    idea_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get a single idea."""
    svc = IdeaService(db)
    idea = await svc.get_by_id(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    return _idea_to_response(idea)


@router.patch("/api/ideas/{idea_id}")
async def update_idea(
    idea_id: str,
    body: IdeaUpdate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Update an idea."""
    svc = IdeaService(db)
    existing = await svc.get_by_id(idea_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Idea not found")

    update_data = {}
    if body.title is not None:
        update_data["title"] = body.title.strip()
    if body.description is not None:
        update_data["description"] = body.description.strip()
    if body.source is not None:
        if body.source not in VALID_SOURCES:
            raise HTTPException(status_code=400, detail=f"source must be one of: {', '.join(VALID_SOURCES)}")
        update_data["source"] = body.source
    if body.category is not None:
        update_data["category"] = body.category if body.category else None
    if body.priority is not None:
        if body.priority not in VALID_PRIORITIES:
            raise HTTPException(status_code=400, detail=f"priority must be one of: {', '.join(VALID_PRIORITIES)}")
        update_data["priority"] = body.priority
    if body.status is not None:
        if body.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(VALID_STATUSES)}")
        update_data["status"] = body.status
    if body.tags is not None:
        update_data["tags"] = body.tags

    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated = await svc.update(idea_id, update_data)
        if not updated:
            raise HTTPException(status_code=404, detail="Idea not found")
        return _idea_to_response(updated)

    return _idea_to_response(existing)


@router.delete("/api/ideas/{idea_id}")
async def delete_idea(
    idea_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Delete an idea."""
    svc = IdeaService(db)
    existing = await svc.get_by_id(idea_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Idea not found")
    await svc.delete(idea_id)
    return {"detail": "Deleted"}


# ── Link / Unlink ────────────────────────────────────

class IdeaLinkRequest(BaseModel):
    target_type: str  # "video", "fact", "analysis"
    target_id: str


@router.post("/api/ideas/{idea_id}/link")
async def link_entity_to_idea(
    idea_id: str,
    body: IdeaLinkRequest,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Link a video, fact, or analysis topic to an idea."""
    svc = IdeaService(db)
    idea = await svc.get_by_id(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    field_map = {"video": "linked_video_ids", "fact": "linked_fact_ids", "analysis": "linked_analysis_ids"}
    field = field_map.get(body.target_type)
    if not field:
        raise HTTPException(status_code=400, detail=f"Invalid target_type: {body.target_type}")
    await svc.collection.update_one({"_id": idea_id}, {"$addToSet": {field: body.target_id}})
    updated = await svc.get_by_id(idea_id)
    return _idea_to_response(updated)


@router.post("/api/ideas/{idea_id}/unlink")
async def unlink_entity_from_idea(
    idea_id: str,
    body: IdeaLinkRequest,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Unlink a video, fact, or analysis topic from an idea."""
    svc = IdeaService(db)
    idea = await svc.get_by_id(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    field_map = {"video": "linked_video_ids", "fact": "linked_fact_ids", "analysis": "linked_analysis_ids"}
    field = field_map.get(body.target_type)
    if not field:
        raise HTTPException(status_code=400, detail=f"Invalid target_type: {body.target_type}")
    await svc.collection.update_one({"_id": idea_id}, {"$pull": {field: body.target_id}})
    updated = await svc.get_by_id(idea_id)
    return _idea_to_response(updated)


# ── Per-Agent Endpoints ──────────────────────────────

@router.get("/api/agents/{agent_id}/ideas")
async def list_agent_ideas(
    agent_id: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    source: Optional[str] = Query(None, description="Filter by source: user or agent"),
    limit: int = Query(200, ge=1, le=500),
    skip: int = Query(0, ge=0),
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List ideas for a specific agent."""
    agent = await AgentService(db).get_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    svc = IdeaService(db)
    items = await svc.get_by_agent(agent_id, status=status, source=source, limit=limit, skip=skip)
    return {"items": [_idea_to_response(i) for i in items], "total": len(items)}


@router.post("/api/agents/{agent_id}/ideas", status_code=201)
async def create_agent_idea(
    agent_id: str,
    body: IdeaCreate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Create an idea for a specific agent."""
    agent = await AgentService(db).get_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(VALID_STATUSES)}")
    if body.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority must be one of: {', '.join(VALID_PRIORITIES)}")

    idea = MongoIdea(
        title=body.title.strip(),
        description=body.description.strip() if body.description else "",
        source=body.source,
        agent_id=agent_id,
        category=body.category,
        priority=body.priority,
        status=body.status,
        tags=body.tags,
        created_by=body.source,
    )
    svc = IdeaService(db)
    created = await svc.create(idea)
    return _idea_to_response(created)
