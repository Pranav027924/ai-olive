"""Auth router — register + login, minting JWTs (PRD §9.4)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from chat_service.application.use_cases.authenticate_user import AuthenticateUserCommand
from chat_service.application.use_cases.register_user import RegisterUserCommand
from chat_service.domain.errors import EmailAlreadyRegistered, InvalidCredentials
from chat_service.interfaces.http.dependencies import (
    AuthenticateUserDep,
    JwtIssuerDep,
    RegisterUserDep,
    SettingsDep,
)
from chat_service.interfaces.http.schemas import (
    AuthUserView,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    handler: RegisterUserDep,
    issuer: JwtIssuerDep,
    settings: SettingsDep,
) -> TokenResponse:
    if not settings.allow_registration:
        raise HTTPException(status_code=403, detail="registration is disabled")
    try:
        user = await handler.handle(RegisterUserCommand(email=body.email, password=body.password))
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=409, detail="email already registered") from exc
    return TokenResponse(access_token=issuer.issue(user.id), user=AuthUserView.from_domain(user))


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    handler: AuthenticateUserDep,
    issuer: JwtIssuerDep,
) -> TokenResponse:
    try:
        user = await handler.handle(
            AuthenticateUserCommand(email=body.email, password=body.password)
        )
    except InvalidCredentials as exc:
        raise HTTPException(
            status_code=401,
            detail="invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return TokenResponse(access_token=issuer.issue(user.id), user=AuthUserView.from_domain(user))
