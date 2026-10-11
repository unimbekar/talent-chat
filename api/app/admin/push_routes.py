"""Turn push alerts on or off for this device, and send a test alert."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.pipeline import require_admin
from app.models import AuditLog, PushSubscription
from app.push import allowed_endpoint, send_to_all, vapid_key

router = APIRouter(prefix="/admin/push", tags=["push"])


class Keys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)
    keys: Keys


class EndpointIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)


@router.get("/key")
def public_key(session: Session = Depends(require_admin)):
    _, key = vapid_key(session)
    devices = session.scalar(select(func.count()).select_from(PushSubscription)) or 0
    return {"public_key": key, "devices": devices}


@router.post("/subscribe")
def subscribe(body: SubscriptionIn, request: Request, session: Session = Depends(require_admin)):
    if not allowed_endpoint(body.endpoint):
        raise HTTPException(status_code=400, detail={"message": "That is not a browser push service."})
    row = session.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if row is None:
        row = PushSubscription(endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth)
        session.add(row)
    row.p256dh = body.keys.p256dh
    row.auth = body.keys.auth
    row.device = (request.headers.get("user-agent") or "")[:300] or None
    session.add(AuditLog(actor="admin", action="push_subscribe", outcome="on"))
    session.commit()
    return {"ok": True}


@router.post("/unsubscribe")
def unsubscribe(body: EndpointIn, session: Session = Depends(require_admin)):
    row = session.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if row is not None:
        session.delete(row)
        session.add(AuditLog(actor="admin", action="push_subscribe", outcome="off"))
        session.commit()
    return {"ok": True}


@router.post("/test")
def test(session: Session = Depends(require_admin)):
    sent = send_to_all(
        session,
        {
            "title": "Alerts are on",
            "body": "You will get one of these for each application on the careers page.",
            "url": "/admin/pipeline",
            "tag": "push-test",
        },
    )
    return {"sent": sent}
