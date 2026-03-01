from typing import Dict, Any

from django.db import transaction
from django.utils import timezone

from base.models import User, Session, PasswordReset, Role
from base.services import ServiceResponse, Validator, CacheService


SESSION_TTL = 72 * 3600  # 72 hours
USER_CACHE_TTL = 600     # 10 min
PERMISSIONS_CACHE_TTL = 300  # 5 min
RATE_LIMIT_TTL = 900     # 15 min window
MAX_LOGIN_ATTEMPTS = 5


class AuthService:

    @classmethod
    @transaction.atomic
    def register(cls, email: str, first_name: str, last_name: str, password: str,
                 ip_address: str = "", user_agent: str = "") -> tuple:
        #validate all fields upfront
        v = Validator()
        v.required(email, "Email").email(email)
        v.required(first_name, "First name").max_length(first_name, 30, "First name")
        v.required(last_name, "Last name").max_length(last_name, 30, "Last name")
        v.required(password, "Password").password_strength(password)

        if not v.is_valid:
            return ServiceResponse.error(v.errors)

        email = email.strip().lower()

        #check if email exists
        if User.objects.filter(email=email).exists():
            return ServiceResponse.error("Email already exists")

        #create the user
        user = User(
            email=email,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
        )
        user.set_password(password)
        user.email_verified_at = None
        user.save()

        #assign default role if one exists
        default_role = Role.objects.filter(is_default=True).first()
        if default_role:
            user.assign_role(default_role.slug)

        #create session right away so they're logged in
        session = Session.create_session(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        #cache the user data
        cls._cache_user(user)

        return ServiceResponse.success(
            message="Registered successfully",
            data={
                "session_key": session.key,
                "user": cls._serialize_user(user),
            },
            status=201,
        )

    @classmethod
    def login(cls, email: str, password: str,
              ip_address: str = "", user_agent: str = "", device: str = "") -> tuple:
        #validate inputs
        v = Validator()
        v.required(email, "Email")
        v.required(password, "Password").min_length(password, 8, "Password")

        if not v.is_valid:
            return ServiceResponse.error(v.errors)

        email = email.strip().lower()

        #check rate limiting -- block brute force
        rate_key = f"login_attempts:{ip_address}"
        attempts = CacheService.get(rate_key) or 0
        if attempts >= MAX_LOGIN_ATTEMPTS:
            return ServiceResponse.error(
                "Too many login attempts. Try again in 15 minutes", status=429
            )

        #find user by email
        user = User.objects.filter(email=email, is_active=True).first()
        if not user or not user.check_password(password):
            #increment failed attempts
            CacheService.set(rate_key, attempts + 1, RATE_LIMIT_TTL)
            return ServiceResponse.error("Invalid credentials", status=401)

        #clear rate limit on success
        CacheService.delete(rate_key)

        #update last login info
        user.last_login_at = timezone.now()
        user.last_login_ip = ip_address
        user.save(update_fields=["last_login_at", "last_login_ip"])

        #create session
        session = Session.create_session(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            device=device,
        )

        #cache user and permissions
        cls._cache_user(user)
        cls._cache_permissions(user)

        return ServiceResponse.success(
            message="Logged in successfully",
            data={
                "session_key": session.key,
                "user": cls._serialize_user(user),
                "permissions": list(user.get_permissions()),
            },
        )

    @classmethod
    def logout(cls, session_key: str) -> tuple:
        #validate session exists
        session = Session.get_valid_session(session_key)
        if not session:
            return ServiceResponse.unauthorized("Invalid or expired session")

        user_id = session.user_id

        #kill the session
        session.invalidate()

        #clear cached data for this user
        CacheService.delete(f"user:{user_id}")
        CacheService.delete(f"permissions:{user_id}")
        CacheService.delete(f"session:{session_key}")

        return ServiceResponse.success("Logged out successfully")

    @classmethod
    def logout_all(cls, session_key: str) -> tuple:
        """kill all sessions for the user -- logout everywhere"""
        session = Session.get_valid_session(session_key)
        if not session:
            return ServiceResponse.unauthorized("Invalid or expired session")

        user = session.user

        #nuke everything
        Session.invalidate_all(user)

        #clear all cached data
        CacheService.delete(f"user:{user.pk}")
        CacheService.delete(f"permissions:{user.pk}")

        return ServiceResponse.success("Logged out from all devices")

    @classmethod
    def me(cls, session_key: str) -> tuple:
        #try cache first for speed
        session = Session.get_valid_session(session_key)
        if not session:
            return ServiceResponse.unauthorized("Invalid or expired session")

        user = session.user

        #check cache before hitting db
        cached = CacheService.get(f"user:{user.pk}")
        if cached:
            return ServiceResponse.success("Profile retrieved", data=cached)

        #build fresh and cache it
        user_data = cls._serialize_user(user)
        user_data["permissions"] = list(user.get_permissions())
        user_data["roles"] = list(user.get_roles())

        CacheService.set(f"user:{user.pk}", user_data, USER_CACHE_TTL)

        return ServiceResponse.success("Profile retrieved", data=user_data)

    @classmethod
    @transaction.atomic
    def change_password(cls, session_key: str, current_password: str, new_password: str) -> tuple:
        session = Session.get_valid_session(session_key)
        if not session:
            return ServiceResponse.unauthorized("Invalid or expired session")

        user = session.user

        #verify current password
        if not user.check_password(current_password):
            return ServiceResponse.error("Current password is incorrect")

        #validate new password
        v = Validator()
        v.required(new_password, "New password").password_strength(new_password)
        if not v.is_valid:
            return ServiceResponse.error(v.errors)

        #set new password and kill all other sessions
        user.set_password(new_password)
        user.save(update_fields=["password"])

        #invalidate all sessions except current
        Session.objects.filter(user=user, is_active=True).exclude(key=session_key).update(is_active=False)

        return ServiceResponse.success("Password changed successfully")

    @classmethod
    def request_password_reset(cls, email: str) -> tuple:
        """always return success to prevent email enumeration"""
        email = email.strip().lower()
        user = User.objects.filter(email=email, is_active=True).first()

        if user:
            reset = PasswordReset.create_token(user)
            #TODO: send email with reset.token
            #email_service.send_reset_email(user.email, reset.token)

        #always return success to not leak whether email exists
        return ServiceResponse.success(
            "If the email exists, a reset link has been sent"
        )

    @classmethod
    @transaction.atomic
    def reset_password(cls, token: str, new_password: str) -> tuple:
        #validate new password
        v = Validator()
        v.required(new_password, "Password").password_strength(new_password)
        if not v.is_valid:
            return ServiceResponse.error(v.errors)

        #find and validate token
        reset = PasswordReset.validate_token(token)
        if not reset:
            return ServiceResponse.error("Invalid or expired reset token")

        user = reset.user

        #set new password
        user.set_password(new_password)
        user.save(update_fields=["password"])

        #consume the token so it cant be reused
        reset.consume()

        #kill all existing sessions
        Session.invalidate_all(user)

        #clear cache
        CacheService.delete(f"user:{user.pk}")

        return ServiceResponse.success("Password reset successfully. Please login again.")

    @classmethod
    def get_active_sessions(cls, session_key: str) -> tuple:
        """let user see all their active sessions"""
        session = Session.get_valid_session(session_key)
        if not session:
            return ServiceResponse.unauthorized("Invalid or expired session")

        sessions = Session.objects.filter(
            user=session.user, is_active=True, expires_at__gt=timezone.now()
        ).values("key", "ip_address", "device", "user_agent", "last_activity_at", "created_at")

        data = []
        for s in sessions:
            data.append({
                "key": s["key"][:12] + "...",
                "ip_address": s["ip_address"],
                "device": s["device"],
                "user_agent": s["user_agent"][:100] if s["user_agent"] else "",
                "last_activity": s["last_activity_at"].isoformat() if s["last_activity_at"] else None,
                "created_at": s["created_at"].isoformat() if s["created_at"] else None,
                "is_current": s["key"] == session_key,
            })

        return ServiceResponse.success("Active sessions", data=data)

    @classmethod
    def revoke_session(cls, session_key: str, target_key: str) -> tuple:
        """revoke a specific session from another device"""
        session = Session.get_valid_session(session_key)
        if not session:
            return ServiceResponse.unauthorized("Invalid or expired session")

        #make sure target session belongs to same user
        target = Session.objects.filter(
            key=target_key, user=session.user, is_active=True
        ).first()

        if not target:
            return ServiceResponse.not_found("Session not found")

        target.invalidate()
        CacheService.delete(f"session:{target_key}")

        return ServiceResponse.success("Session revoked")

    @classmethod
    def _serialize_user(cls, user: User) -> dict:
        return {
            "id": user.pk,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "phone": user.phone,
            "is_active": user.is_active,
            "email_verified": user.email_verified_at is not None,
            "last_login": user.last_login_at.isoformat() if user.last_login_at else None,
        }

    @classmethod
    def _cache_user(cls, user: User) -> None:
        CacheService.set(f"user:{user.pk}", cls._serialize_user(user), USER_CACHE_TTL)

    @classmethod
    def _cache_permissions(cls, user: User) -> None:
        perms = list(user.get_permissions())
        CacheService.set(f"permissions:{user.pk}", perms, PERMISSIONS_CACHE_TTL)

    @classmethod
    def get_cached_permissions(cls, user_id: int) -> list:
        """used by middleware for fast permission checks"""
        cached = CacheService.get(f"permissions:{user_id}")
        if cached is not None:
            return cached

        try:
            user = User.objects.get(pk=user_id)
            perms = list(user.get_permissions())
            CacheService.set(f"permissions:{user_id}", perms, PERMISSIONS_CACHE_TTL)
            return perms
        except User.DoesNotExist:
            return []