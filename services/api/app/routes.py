import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Identity, get_current_identity, get_current_user
from app.database import get_db_session
from app.models import Agent, Membership, Organization, User
from app.schemas import AgentCreate, AgentRead, AgentUpdate, OrganizationCreate, OrganizationRead

router = APIRouter(prefix="/v1")


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
