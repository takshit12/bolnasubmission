#!/usr/bin/env python3

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from datetime import datetime
import hmac
import hashlib
import time
from typing import Dict

from event_handler import event_handler

app = FastAPI(
    title="Status Page Webhook Receiver",
    version="1.0.0"
)


def verify_svix_signature(
    payload: bytes,
    webhook_id: str,
    webhook_timestamp: str,
    webhook_signature: str,
    secret: str
) -> bool:
    try:
        current_time = int(time.time())
        timestamp = int(webhook_timestamp)
        if abs(current_time - timestamp) > 300:
            return False
    except (ValueError, TypeError):
        return False

    signed_content = f"{webhook_id}.{webhook_timestamp}.{payload.decode('utf-8')}"
    expected_sig = hmac.new(
        secret.encode('utf-8'),
        signed_content.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    if ',' in webhook_signature:
        actual_sig = webhook_signature.split(',')[1]
    else:
        actual_sig = webhook_signature

    return hmac.compare_digest(expected_sig, actual_sig)


def verify_hmac_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected_sig = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    if signature.startswith('sha256='):
        signature = signature[7:]

    return hmac.compare_digest(expected_sig, signature)


async def process_webhook_async(provider: str, event_data: Dict):
    await event_handler.handle_webhook_event(event_data, provider)


@app.get("/")
async def root():
    return {
        "service": "Status Page Webhook Receiver",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "incident.io": "/webhook/incident-io",
            "generic": "/webhook/generic/{provider_name}",
            "health": "/health"
        }
    }


@app.post("/webhook/incident-io")
async def receive_incident_io_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    payload = await request.body()

    webhook_id = request.headers.get("webhook-id")
    webhook_timestamp = request.headers.get("webhook-timestamp")
    webhook_signature = request.headers.get("webhook-signature")

    try:
        event_data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    background_tasks.add_task(process_webhook_async, "incident.io", event_data)

    return JSONResponse(
        status_code=200,
        content={"status": "received", "timestamp": datetime.utcnow().isoformat()}
    )


@app.post("/webhook/generic/{provider_name}")
async def receive_generic_webhook(
    provider_name: str,
    request: Request,
    background_tasks: BackgroundTasks
):
    payload = await request.body()
    x_signature = request.headers.get("X-Signature") or request.headers.get("X-Hub-Signature-256")

    try:
        event_data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    background_tasks.add_task(process_webhook_async, provider_name, event_data)

    return JSONResponse(
        status_code=200,
        content={"status": "received", "timestamp": datetime.utcnow().isoformat()}
    )


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "seen_incidents": len(event_handler.seen_incidents)
    }


@app.get("/stats")
async def stats():
    return {
        "seen_incidents_count": len(event_handler.seen_incidents),
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    print("Starting webhook receiver on http://localhost:8000")
    print("Use ngrok to expose for testing: ngrok http 8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
