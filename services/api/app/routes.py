import asyncio
import logging
import time
import uuid
from collections import defaultdict
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Identity, get_current_identity, get_current_user
from app.database import get_db_session
from app.kokoro_service import SUPPORTED_LANGUAGES, VOICE_LANGUAGES, KokoroService
from app.models import Agent, Membership, Organization, User, VoiceSetting
from app.schemas import AgentCreate, AgentRead, AgentUpdate, OrganizationCreate, OrganizationRead
from app.settings import Settings, get_settings

router = APIRouter(prefix="/v1")
logger = logging.getLogger("volvox.api")
_inference_slots = asyncio.Semaphore(1)
_chat_histories: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
_chat_locks: dict[tuple[str, str], asyncio.Lock] = defaultdict(asyncio.Lock)


class SpeechRequest(BaseModel):
    text: str = Field(max_length=5000)
    voice_id: str = Field(default="af_sarah", min_length=1, max_length=64)
    language: str = Field(default="en-us", min_length=2, max_length=16)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str = Field(min_length=1, max_length=64)
    agent_id: uuid.UUID | None = None


class VoiceSettingWrite(BaseModel):
    voice_id: str = Field(min_length=1, max_length=64)
    language: str = Field(default="en-us", min_length=2, max_length=16)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    agent_id: uuid.UUID | None = None


def _service(request: Request) -> KokoroService:
    return cast(KokoroService, request.app.state.kokoro)


@router.get("/voices")
def list_voices(request: Request) -> dict[str, object]:
    service = _service(request)
    return {"voices": [{"id": voice, "language": VOICE_LANGUAGES.get(voice)} for voice in service.voices], "languages": sorted(SUPPORTED_LANGUAGES), "available": bool(service.voices)}


@router.post("/organizations/{organization_id}/speech")
async def generate_speech(organization_id: uuid.UUID, payload: SpeechRequest, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db_session)) -> Response:
    require_membership(db, user, organization_id)
    service = _service(request)
    if not service.voices:
        raise HTTPException(status_code=503, detail="Speech generation is unavailable. Check the local voice model setup.")
    try:
        await asyncio.wait_for(_inference_slots.acquire(), timeout=2)
    except TimeoutError as exc:
        raise HTTPException(status_code=429, detail="Speech generation is busy. Try again shortly.") from exc
    started = time.monotonic()
    try:
        audio, sample_rate = await asyncio.wait_for(asyncio.to_thread(service.synthesize, payload.text, payload.voice_id, payload.language, payload.speed), timeout=45)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Speech generation took too long. Try a shorter text.") from exc
    except Exception as exc:
        logger.exception("speech_generation_failed", extra={"organization_id": str(organization_id)})
        raise HTTPException(status_code=502, detail="Speech generation failed. Please try again.") from exc
    finally:
        _inference_slots.release()
    logger.info("speech_generated", extra={"organization_id": str(organization_id), "characters": len(payload.text), "duration_ms": round((time.monotonic()-started)*1000)})
    return RawResponse(audio, media_type="audio/wav", headers={"x-audio-sample-rate": str(sample_rate), "cache-control": "no-store"})


@router.post("/organizations/{organization_id}/chat")
async def chat(organization_id: uuid.UUID, payload: ChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db_session), settings: Settings = Depends(get_settings)) -> dict[str, str]:
    require_membership(db, user, organization_id)
    agent = None
    if payload.agent_id:
        agent = db.scalar(select(Agent).where(Agent.id == payload.agent_id, Agent.organization_id == organization_id))
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
    key = (str(organization_id), f"{user.id}:{payload.agent_id or 'default'}:{payload.conversation_id}")
    async with _chat_locks[key]:
        return await _chat_turn(key, payload, organization_id, settings, agent)


async def _chat_turn(key: tuple[str, str], payload: ChatRequest, organization_id: uuid.UUID, settings: Settings, agent: Agent | None = None) -> dict[str, str]:
    history = _chat_histories[key]
    messages = ([{"role": "system", "content": agent.instructions}] if agent and agent.instructions.strip() else []) + history
    messages.append({"role": "user", "content": payload.message})
    try:
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{settings.ollama_host.rstrip('/')}/api/chat", json={"model": settings.chat_model, "messages": messages, "stream": False})
            response.raise_for_status()
            answer = response.json()["message"]["content"]
    except Exception as exc:
        logger.exception("ollama_chat_failed", extra={"organization_id": str(organization_id)})
        raise HTTPException(status_code=502, detail="Local Ollama could not generate a response.") from exc
    history.append({"role": "user", "content": payload.message})
    history.append({"role": "assistant", "content": answer})
    history[:] = history[-12:]
    return {"response": answer}


@router.get("/organizations/{organization_id}/voice-settings")
def read_voice_settings(organization_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db_session)) -> list[dict[str, object]]:
    require_membership(db, user, organization_id)
    settings = db.scalars(select(VoiceSetting).where(VoiceSetting.organization_id == organization_id)).all()
    return [{"id": str(item.id), "organization_id": str(item.organization_id), "agent_id": str(item.agent_id) if item.agent_id else None, "voice_id": item.voice_id, "language": item.language, "speed": item.speed} for item in settings]


@router.put("/organizations/{organization_id}/voice-settings")
def save_voice_settings(organization_id: uuid.UUID, payload: VoiceSettingWrite, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db_session)) -> dict[str, object]:
    require_membership(db, user, organization_id, write=True)
    service = _service(request)
    if payload.voice_id not in service.voices:
        raise HTTPException(status_code=422, detail="Choose an installed Kokoro voice.")
    if VOICE_LANGUAGES.get(payload.voice_id) != payload.language:
        raise HTTPException(status_code=422, detail="That language is not supported by the selected voice.")
    if payload.agent_id and db.scalar(select(Agent).where(Agent.id == payload.agent_id, Agent.organization_id == organization_id)) is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    current = db.scalar(select(VoiceSetting).where(VoiceSetting.organization_id == organization_id, VoiceSetting.agent_id == payload.agent_id))
    if current is None:
        current = VoiceSetting(organization_id=organization_id, **payload.model_dump())
        db.add(current)
    else:
        current.voice_id, current.language, current.speed = payload.voice_id, payload.language, payload.speed
    db.commit()
    db.refresh(current)
    return {"id": str(current.id), "organization_id": str(current.organization_id), "agent_id": str(current.agent_id) if current.agent_id else None, "voice_id": current.voice_id, "language": current.language, "speed": current.speed}


def require_membership(
    db: Session, user: User, organization_id: uuid.UUID, *, write: bool = False
) -> Membership:
    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == user.id,
            Membership.auth_subject == user.auth_subject,
            Membership.active.is_(True),
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if write and membership.role not in {"owner", "admin", "operator"}:
        raise HTTPException(status_code=403, detail="Insufficient organization role")
    return membership


@router.get("/organizations", response_model=list[OrganizationRead])
def list_organizations(
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> list[Organization]:
    return list(
        db.scalars(
            select(Organization)
            .join(Membership, Membership.organization_id == Organization.id)
            .join(
                User,
                (User.id == Membership.user_id) & (User.auth_subject == Membership.auth_subject),
            )
            .where(
                User.auth_subject == identity.subject,
                User.active.is_(True),
                Membership.active.is_(True),
            )
        ).all()
    )


@router.post("/organizations", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Organization:
    user = db.scalar(
        select(User).where(User.auth_subject == identity.subject, User.active.is_(True))
    )
    if user is None:
        raise HTTPException(status_code=403, detail="User is not provisioned")
    organization = Organization(name=payload.name.strip())
    db.add(organization)
    db.flush()
    db.add(
        Membership(
            organization_id=organization.id,
            user_id=user.id,
            auth_subject=user.auth_subject,
            role="owner",
            active=True,
        )
    )
    db.commit()
    db.refresh(organization)
    return organization


@router.get("/organizations/{organization_id}", response_model=OrganizationRead)
def get_organization(
    organization_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> Organization:
    require_membership(db, user, organization_id)
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


@router.get("/organizations/{organization_id}/agents", response_model=list[AgentRead])
def list_agents(
    organization_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[Agent]:
    require_membership(db, user, organization_id)
    return list(db.scalars(select(Agent).where(Agent.organization_id == organization_id)).all())


@router.post(
    "/organizations/{organization_id}/agents",
    response_model=AgentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_agent(
    organization_id: uuid.UUID,
    payload: AgentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> Agent:
    require_membership(db, user, organization_id, write=True)
    agent = Agent(organization_id=organization_id, **payload.model_dump())
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/organizations/{organization_id}/agents/{agent_id}", response_model=AgentRead)
def get_agent(
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> Agent:
    require_membership(db, user, organization_id)
    agent = db.scalar(
        select(Agent).where(Agent.organization_id == organization_id, Agent.id == agent_id)
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/organizations/{organization_id}/agents/{agent_id}", response_model=AgentRead)
def update_agent(
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> Agent:
    require_membership(db, user, organization_id, write=True)
    agent = db.scalar(
        select(Agent).where(Agent.organization_id == organization_id, Agent.id == agent_id)
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(agent, key, value)
    db.commit()
    db.refresh(agent)
    return agent


@router.delete(
    "/organizations/{organization_id}/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_agent(
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> Response:
    require_membership(db, user, organization_id, write=True)
    agent = db.scalar(
        select(Agent).where(Agent.organization_id == organization_id, Agent.id == agent_id)
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
