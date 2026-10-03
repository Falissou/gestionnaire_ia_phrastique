"""Pharmacy stock-management API and lightweight web application."""

from datetime import date, datetime
from email.message import EmailMessage
import logging
import smtplib
import ssl
from typing import Literal
from urllib.error import URLError

import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from jwt import PyJWKClient
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

from pharmacy_platform.config import ROOT, Settings
from pharmacy_platform.workbooks import WorkbookStore

logger = logging.getLogger(__name__)
settings = Settings()
store = WorkbookStore(settings.data_dir)
app = FastAPI(title="Gestion de stock pharmacie", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
bearer = HTTPBearer(auto_error=False)


class ProductInput(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    category: str = Field(default="Médicament", max_length=100)
    quantity: int = Field(ge=0)
    min_quantity: int = Field(default=5, ge=0)
    unit_price: float = Field(default=0, ge=0)
    expiry_date: date | None = None


class CommandInput(BaseModel):
    product_name: str = Field(min_length=1, max_length=150)
    quantity: int = Field(gt=0)
    supplier: str = Field(min_length=1, max_length=150)
    expected_date: date | None = None


class MovementInput(BaseModel):
    product_id: str
    type: Literal["entree", "sortie"]
    quantity: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=250)
    reference: str | None = Field(default=None, max_length=100)


class ChatInput(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class CommandStatusInput(BaseModel):
    status: Literal["En attente", "Commandée", "Reçue", "Annulée"]


class AlertEmailInput(BaseModel):
    recipient: str = Field(min_length=3, max_length=254)


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    if not settings.auth_enabled:
        return
    if not (settings.entra_tenant_id and settings.entra_api_audience and settings.entra_jwks_url):
        raise HTTPException(status_code=503, detail="Configuration d'authentification Entra incomplète.")
    if credentials is None:
        raise HTTPException(status_code=401, detail="Jeton Bearer requis.")
    try:
        key = PyJWKClient(settings.entra_jwks_url).get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            key.key,
            algorithms=["RS256"],
            audience=settings.entra_api_audience,
            issuer=f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0",
        )
        if claims.get("tid") != settings.entra_tenant_id:
            raise HTTPException(status_code=401, detail="Jeton émis par un tenant non autorisé.")
    except HTTPException:
        raise
    except (URLError, jwt.PyJWKClientConnectionError) as exc:
        raise HTTPException(status_code=503, detail="Impossible de vérifier le jeton auprès d'Entra ID.") from exc
    except (jwt.PyJWTError, jwt.PyJWKClientError) as exc:
        raise HTTPException(status_code=401, detail="Jeton d'authentification invalide.") from exc


def make_alerts() -> list[dict]:
    today = date.today()
    alerts = []
    for product in store.products():
        quantity = product.get("quantity") or 0
        minimum = product.get("min_quantity") or 0
        if quantity <= minimum:
            alerts.append({
                "type": "stock_faible",
                "severity": "high" if quantity == 0 else "medium",
                "product": product["name"],
                "message": f"Stock faible : {quantity} unité(s), seuil {minimum}.",
            })
        expiry = product.get("expiry_date")
        if expiry:
            try:
                if isinstance(expiry, datetime):
                    expiry_date = expiry.date()
                elif isinstance(expiry, date):
                    expiry_date = expiry
                else:
                    expiry_date = date.fromisoformat(str(expiry)[:10])
                days = (expiry_date - today).days
            except (TypeError, ValueError):
                continue
            if days < 0:
                alerts.append({
                    "type": "perime",
                    "severity": "critical",
                    "product": product["name"],
                    "message": f"Produit périmé depuis {abs(days)} jour(s) — retirer du stock.",
                })
            elif days <= 90:
                alerts.append({
                    "type": "expiration_proche",
                    "severity": "high" if days <= 30 else "medium",
                    "product": product["name"],
                    "message": f"Expiration dans {days} jour(s), le {expiry_date.isoformat()}.",
                })
    return alerts


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/agents", dependencies=[Depends(require_auth)])
def agents() -> list[dict]:
    return [{"name": name, "role": role} for name, role in settings.agent_roles.items()]


@app.get("/api/products", dependencies=[Depends(require_auth)])
def products() -> list[dict]:
    return store.products()


@app.post("/api/products", status_code=201, dependencies=[Depends(require_auth)])
def create_product(payload: ProductInput) -> dict:
    return store.add_product(payload.model_dump(mode="json"))


@app.get("/api/commands", dependencies=[Depends(require_auth)])
def commands() -> list[dict]:
    return store.commands()


@app.post("/api/commands", status_code=201, dependencies=[Depends(require_auth)])
def create_command(payload: CommandInput) -> dict:
    return store.add_command(payload.model_dump(mode="json"))


@app.patch("/api/commands/{command_id}", dependencies=[Depends(require_auth)])
def update_command(command_id: str, payload: CommandStatusInput) -> dict:
    command = store.update_command_status(command_id, payload.status)
    if command is None:
        raise HTTPException(status_code=404, detail="Commande introuvable.")
    return command


@app.get("/api/movements", dependencies=[Depends(require_auth)])
def movements() -> list[dict]:
    return store.movements()


@app.post("/api/movements", status_code=201, dependencies=[Depends(require_auth)])
def create_movement(payload: MovementInput) -> dict:
    try:
        return store.add_movement(payload.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/alerts", dependencies=[Depends(require_auth)])
def alerts() -> list[dict]:
    return make_alerts()


@app.get("/api/dashboard", dependencies=[Depends(require_auth)])
def dashboard() -> dict:
    product_rows = store.products()
    command_rows = store.commands()
    alert_rows = make_alerts()
    value = sum((row.get("quantity") or 0) * (row.get("unit_price") or 0) for row in product_rows)
    return {
        "product_count": len(product_rows),
        "total_units": sum(row.get("quantity") or 0 for row in product_rows),
        "inventory_value": round(value, 2),
        "low_stock_count": sum(row["type"] == "stock_faible" for row in alert_rows),
        "expiry_alert_count": sum(row["type"] in ("perime", "expiration_proche") for row in alert_rows),
        "pending_commands": sum(row.get("status") == "En attente" for row in command_rows),
        "alerts": alert_rows[:8],
        "recent_movements": sorted(store.movements(), key=lambda row: str(row.get("date", "")), reverse=True)[:6],
    }


def _foundry_reply(agent_name: str, message: str, context: dict) -> str:
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    if not settings.foundry_project_endpoint:
        raise HTTPException(status_code=503, detail="FOUNDRY_PROJECT_ENDPOINT n'est pas configuré.")
    prompt = (
        f"Contexte opérationnel actuel (données des classeurs Excel):\n{context}\n\n"
        f"Demande de l'utilisateur:\n{message}"
    )
    try:
        with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                endpoint=settings.foundry_project_endpoint,
                credential=credential,
                allow_preview=True,
            ) as project,
        ):
            with project.get_openai_client(agent_name=agent_name) as client:
                response = client.responses.create(input=prompt)
                if response.output_text:
                    return response.output_text
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Foundry agent request failed for %s", agent_name)
        raise HTTPException(status_code=502, detail="Échec de l'appel à l'agent Foundry.") from exc
    raise HTTPException(status_code=502, detail="L'agent Foundry n'a retourné aucune réponse.")


@app.post("/api/agents/{agent_name}/chat", dependencies=[Depends(require_auth)])
def chat(agent_name: str, payload: ChatInput) -> dict:
    if agent_name not in settings.agent_roles:
        raise HTTPException(status_code=404, detail="Agent inconnu ou non configuré.")
    alert_rows = make_alerts()
    dashboard_data = dashboard()
    context = {
        "stock": store.products(),
        "commandes": store.commands(),
        "mouvements": store.movements(),
        "alertes": alert_rows,
        "recommandations": [
            {"priority": item["severity"], "product": item["product"], "action": item["message"]}
            for item in alert_rows
        ],
        "indicateurs_tableau_de_bord": {
            key: dashboard_data[key]
            for key in ("product_count", "total_units", "inventory_value", "pending_commands")
        },
        "envoi_email_configure": bool(settings.smtp_host and settings.smtp_from),
    }
    if agent_name == settings.foundry_agent_names[3]:
        context["analyses_agents_specialises"] = {
            specialist: _foundry_reply(specialist, payload.message, context)
            for specialist in settings.foundry_agent_names[:3]
        }
    reply = _foundry_reply(agent_name, payload.message, context)
    return {"agent": agent_name, "reply": reply}


@app.get("/api/recommendations", dependencies=[Depends(require_auth)])
def recommendations() -> dict:
    alerts_list = make_alerts()
    suggestions = [
        {"priority": item["severity"], "product": item["product"], "action": item["message"]}
        for item in alerts_list
    ]
    return {"recommendations": suggestions, "generated_at": datetime.now().isoformat()}


@app.post("/api/alerts/email", dependencies=[Depends(require_auth)])
def email_alerts(payload: AlertEmailInput) -> dict:
    if not (settings.smtp_host and settings.smtp_from):
        raise HTTPException(
            status_code=503,
            detail="Envoi d'e-mails indisponible : configurez SMTP_HOST et SMTP_FROM.",
        )
    alerts_list = make_alerts()
    message = EmailMessage()
    message["Subject"] = f"PharmaStock — {len(alerts_list)} alerte(s) à traiter"
    message["From"] = settings.smtp_from
    message["To"] = payload.recipient
    message.set_content(
        "Alertes de stock et d'expiration de la pharmacie :\n\n"
        + ("\n".join(f"- {item['product']}: {item['message']}" for item in alerts_list)
           if alerts_list else "Aucune alerte active.")
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls(context=ssl.create_default_context())
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        logger.exception("Alert email delivery failed")
        raise HTTPException(status_code=502, detail="Échec de l'envoi du courriel.") from exc
    return {"sent": True, "recipient": payload.recipient, "alert_count": len(alerts_list)}


frontend = ROOT / "frontend"
if frontend.is_dir():
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
