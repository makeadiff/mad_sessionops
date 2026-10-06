"""
Authentication API Endpoints.

=============================================================================
API ROUTE DESIGN IN DJANGO NINJA
=============================================================================

Django Ninja uses a Router pattern (similar to Express.js or FastAPI):

1. Create a Router instance
2. Define routes with decorators (@router.post, @router.get, etc.)
3. Register router with main API

ROUTE STRUCTURE:
================
All auth routes are prefixed with /api/v1/auth/

    POST /api/v1/auth/register     -> Register with email/password
    POST /api/v1/auth/login        -> Login with email/password
    POST /api/v1/auth/google       -> Login with Google
    POST /api/v1/auth/refresh      -> Refresh access token
    POST /api/v1/auth/logout       -> Logout (blacklist token)
    GET  /api/v1/auth/me           -> Get current user
    PUT  /api/v1/auth/me           -> Update current user
    POST /api/v1/auth/link-google  -> Link Google to account
    POST /api/v1/auth/password/change -> Change password

AUTHENTICATION:
===============
Some routes require authentication (@router.post("/me", auth=jwt_auth))
Others are public (@router.post("/login"))

=============================================================================
"""

from ninja import Router
from ninja.errors import HttpError

from sessionops.auth import CustomJwtAuthMiddleware
from sessionops.schemas import (
    AuthResponseSchema,
    ChangePasswordSchema,
    ErrorResponseSchema,
    ForgotPasswordSchema,
    GoogleAuthSchema,
    LoginSchema,
    LogoutSchema,
    MessageResponseSchema,
    PermissionsResponseSchema,
    RefreshTokenSchema,
    RegisterSchema,
    ResetPasswordSchema,
    SetPasswordSchema,
    TokenResponseSchema,
    UserResponseSchema,
    UserUpdateSchema,
    user_to_response,
)
from sessionops.services import AuthService
from sessionops.services.auth_service import AuthenticationError
from sessionops.utils.custom_logger import get_logger

logger = get_logger(__name__)

# =============================================================================
# ROUTER SETUP
# =============================================================================
# Router groups related endpoints together
# Tags appear in OpenAPI/Swagger documentation
# =============================================================================

auth_router = Router(tags=["Authentication"])

# JWT authentication instance (reused across protected routes)
jwt_auth = CustomJwtAuthMiddleware()


# =============================================================================
# HELPER FUNCTION FOR ERROR RESPONSES
# =============================================================================


def handle_auth_error(error: AuthenticationError):
    """
    Convert AuthenticationError to appropriate HTTP response.

    Maps error codes to HTTP status codes:
    - INVALID_CREDENTIALS -> 401 Unauthorized
    - EMAIL_EXISTS -> 409 Conflict
    - Others -> 400 Bad Request
    """
    status_map = {
        "INVALID_CREDENTIALS": 401,
        "INVALID_REFRESH_TOKEN": 401,
        "INVALID_GOOGLE_TOKEN": 401,
        "EMAIL_EXISTS": 409,
        "GOOGLE_ALREADY_LINKED": 409,
        "GOOGLE_ALREADY_USED": 409,
        "NO_PASSWORD_AUTH": 400,
        "WRONG_PASSWORD": 400,
        "EMAIL_NOT_FOUND": 404,
    }

    status = status_map.get(error.error_code, 400)
    raise HttpError(status, error.message)


# =============================================================================
# PUBLIC ENDPOINTS (No Authentication Required)
# =============================================================================


@auth_router.post(
    "/register",
    auth=None,  # Public endpoint - no authentication required
    response={201: AuthResponseSchema, 400: ErrorResponseSchema, 409: ErrorResponseSchema},
    summary="Register a new user",
    description="""
    Register a new user with email and password.

    **Password Requirements:**
    - At least 8 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 number

    **Returns:**
    - User information
    - JWT access and refresh tokens
    """,
)
def register(request, data: RegisterSchema):
    """
    Register a new user with email and password.

    This endpoint creates both a User record and a UserAuth record
    for password-based authentication.

    Example Request:
        POST /api/v1/auth/register
        Content-Type: application/json

        {
            "email": "john@example.com",
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
            "user_display_name": "John Doe"
        }

    Example Response (201):
        {
            "user": {
                "user_id": 1,
                "email": "john@example.com",
                "user_display_name": "John Doe",
                ...
            },
            "tokens": {
                "access_token": "eyJ...",
                "refresh_token": "eyJ...",
                "token_type": "Bearer",
                "expires_in": 43200
            }
        }
    """
    try:
        result = AuthService.register_with_password(data)
        return 201, result
    except AuthenticationError as e:
        handle_auth_error(e)


@auth_router.post(
    "/login",
    auth=None,  # Public endpoint - no authentication required
    response={200: AuthResponseSchema, 401: ErrorResponseSchema},
    summary="Login with email and password",
    description="""
    Authenticate a user with email and password.

    **Returns:**
    - User information
    - JWT access and refresh tokens

    **Token Usage:**
    - Include access_token in Authorization header: `Bearer <token>`
    - Use refresh_token to get new access_token when expired
    """,
)
def login(request, data: LoginSchema):
    """
    Authenticate user with email and password.

    Example Request:
        POST /api/v1/auth/login
        Content-Type: application/json

        {
            "email": "john@example.com",
            "password": "SecurePass123!"
        }

    Example Response (200):
        {
            "user": { ... },
            "tokens": {
                "access_token": "eyJ...",
                "refresh_token": "eyJ...",
                "token_type": "Bearer",
                "expires_in": 43200
            }
        }
    """
    try:
        result = AuthService.login_with_password(data)
        return result
    except AuthenticationError as e:
        handle_auth_error(e)


@auth_router.post(
    "/google/oauth/callback",
    auth=None,  # Public endpoint - no authentication required
    response={200: AuthResponseSchema, 401: ErrorResponseSchema},
    summary="Login or register with Google",
    description="""
    Authenticate with Google OAuth.

    **Flow:**
    1. Frontend initiates Google Sign-In
    2. Google returns ID token to frontend
    3. Frontend sends ID token to this endpoint
    4. Backend verifies token and logs in or creates user

    **Behavior:**
    - If Google account is already linked -> Login
    - If email exists but Google not linked -> Link Google and login
    - If new email -> Create user and login
    """,
)
def google_auth(request, data: GoogleAuthSchema):
    logger.info("=== Google Auth Endpoint Hit ===")
    logger.info(f"Received code: {data.code[:20]}...")
    logger.info(f"Received codeVerifier: {data.codeVerifier[:20]}...")
    logger.info(f"Received redirectUri: {data.redirectUri}")

    try:
        logger.info("Calling AuthService.login_with_google")
        result = AuthService.login_with_google(
            code=data.code,
            code_verifier=data.codeVerifier,
            redirect_uri=data.redirectUri,
        )
        logger.info("=== AuthService.login_with_google returned successfully ===")
        logger.info(f"Result type: {type(result)}")
        logger.info(f"Result user email: {result.user.email}")
        logger.info(f"Result tokens.access_token exists: {bool(result.tokens.access_token)}")
        logger.info(f"Result tokens.refresh_token exists: {bool(result.tokens.refresh_token)}")
        logger.info(f"Access token (first 50 chars): {result.tokens.access_token[:50]}...")
        logger.info("=== Returning result to frontend ===")
        return result
    except AuthenticationError as e:
        logger.error(f"AuthenticationError: {e.message} (code: {e.error_code})")
        handle_auth_error(e)


@auth_router.post(
    "/refresh",
    auth=None,  # Public endpoint - no authentication required (uses refresh token)
    response={200: TokenResponseSchema, 401: ErrorResponseSchema},
    summary="Refresh access token",
    description="""
    Get a new access token using a refresh token.

    **When to use:**
    - Access token has expired
    - API returns 401 Unauthorized

    **Note:**
    - Refresh token may be rotated (new one returned)
    - Old refresh token becomes invalid after rotation
    """,
)
def refresh_token(request, data: RefreshTokenSchema):
    """
    Refresh the access token.

    Example Request:
        POST /api/v1/auth/refresh
        Content-Type: application/json

        {
            "refresh_token": "eyJ..."
        }

    Example Response (200):
        {
            "access_token": "eyJ...",
            "refresh_token": "eyJ...",  // May be new if rotation enabled
            "token_type": "Bearer",
            "expires_in": 43200
        }
    """
    try:
        result = AuthService.refresh_tokens(data.refresh_token)
        return result
    except AuthenticationError as e:
        handle_auth_error(e)


# =============================================================================
# PROTECTED ENDPOINTS (Authentication Required)
# =============================================================================


@auth_router.get(
    "/me",
    auth=jwt_auth,
    response={200: UserResponseSchema, 401: ErrorResponseSchema},
    summary="Get current user",
    description="Get information about the currently authenticated user.",
)
def get_current_user(request):
    """
    Get the current authenticated user's information.

    Example Request:
        GET /api/v1/auth/me
        Authorization: Bearer eyJ...

    Example Response (200):
        {
            "user_id": 1,
            "email": "john@example.com",
            "user_display_name": "John Doe",
            "user_role": "user",
            "auth_methods": ["password", "google_oauth"],
            ...
        }
    """
    # request.user is set by CustomJwtAuthMiddleware
    # But it's using Django's User model, we need our User model
    from sessionops.models import User

    # Get user_id from token payload
    user_id = getattr(request, "user", None)
    if user_id and hasattr(user_id, "id"):
        # CustomJwtAuthMiddleware sets request.user to Django User
        # We need to look up our custom User model
        # For now, let's get user by email since that's what we have
        email = user_id.email if user_id else None
        if email:
            try:
                user = User.objects.get(email=email)
                return user_to_response(user)
            except User.DoesNotExist:
                pass

    raise HttpError(401, "User not found")


@auth_router.put(
    "/me",
    auth=jwt_auth,
    response={200: UserResponseSchema, 401: ErrorResponseSchema},
    summary="Update current user",
    description="Update the current user's profile information.",
)
def update_current_user(request, data: UserUpdateSchema):
    """
    Update the current authenticated user's profile.

    Only provided fields will be updated.

    Example Request:
        PUT /api/v1/auth/me
        Authorization: Bearer eyJ...
        Content-Type: application/json

        {
            "user_display_name": "John Smith",
            "city": "Mumbai"
        }

    Example Response (200):
        {
            "user_id": 1,
            "email": "john@example.com",
            "user_display_name": "John Smith",
            "city": "Mumbai",
            ...
        }
    """
    from sessionops.models import User

    # Get user from token
    user_id = getattr(request, "user", None)
    if not user_id or not hasattr(user_id, "email"):
        raise HttpError(401, "User not found")

    try:
        user = User.objects.get(email=user_id.email)
    except User.DoesNotExist:
        raise HttpError(401, "User not found")

    # Update only provided fields
    update_data = data.dict(exclude_unset=True, exclude_none=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    user.save()

    return user_to_response(user)


@auth_router.post(
    "/logout",
    auth=jwt_auth,
    response={200: MessageResponseSchema, 401: ErrorResponseSchema},
    summary="Logout user",
    description="""
    Logout the current user by blacklisting their refresh token.

    **Note:**
    - The refresh token will no longer work
    - The access token remains valid until expiry
    - For immediate access revocation, clear tokens on frontend
    """,
)
def logout(request, data: LogoutSchema):
    """
    Logout the user by blacklisting their refresh token.

    Example Request:
        POST /api/v1/auth/logout
        Authorization: Bearer eyJ...
        Content-Type: application/json

        {
            "refresh_token": "eyJ..."
        }

    Example Response (200):
        {
            "message": "Successfully logged out",
            "success": true
        }
    """
    try:
        AuthService.logout(data.refresh_token)
        return MessageResponseSchema(message="Successfully logged out", success=True)
    except AuthenticationError as e:
        handle_auth_error(e)


@auth_router.post(
    "/link-google",
    auth=jwt_auth,
    response={200: MessageResponseSchema, 400: ErrorResponseSchema, 409: ErrorResponseSchema},
    summary="Link Google account",
    description="""
    Link a Google account to an existing user account.

    **Use case:**
    User registered with password and wants to add Google login.

    **Restrictions:**
    - Cannot link if Google already linked
    - Cannot link if Google account used by another user
    """,
)
def link_google(request, data: GoogleAuthSchema):
    """
    Link Google OAuth to the current user's account.

    Example Request:
        POST /api/v1/auth/link-google
        Authorization: Bearer eyJ...
        Content-Type: application/json

        {
            "id_token": "eyJ..."
        }

    Example Response (200):
        {
            "message": "Google account linked successfully",
            "success": true
        }
    """
    from sessionops.models import User

    # Get user from token
    user_id = getattr(request, "user", None)
    if not user_id or not hasattr(user_id, "email"):
        raise HttpError(401, "User not found")

    try:
        user = User.objects.get(email=user_id.email)
    except User.DoesNotExist:
        raise HttpError(401, "User not found")

    try:
        AuthService.link_google_account(
            user,
            code=data.code,
            code_verifier=data.codeVerifier,
            redirect_uri=data.redirectUri,
        )
        return MessageResponseSchema(
            message="Google account linked successfully",
            success=True,
        )
    except AuthenticationError as e:
        handle_auth_error(e)


@auth_router.post(
    "/password/change",
    auth=jwt_auth,
    response={200: MessageResponseSchema, 400: ErrorResponseSchema},
    summary="Change password",
    description="""
    Change the current user's password.

    **Requirements:**
    - User must have password authentication set up
    - Old password must be correct
    - New password must meet strength requirements
    """,
)
def change_password(request, data: ChangePasswordSchema):
    from sessionops.models import User

    user_id = getattr(request, "user", None)
    if not user_id or not hasattr(user_id, "email"):
        raise HttpError(401, "User not found")

    try:
        user = User.objects.get(email=user_id.email)
    except User.DoesNotExist:
        raise HttpError(401, "User not found")

    try:
        AuthService.change_password(user, data)
        return MessageResponseSchema(message="Password changed successfully", success=True)
    except AuthenticationError as e:
        handle_auth_error(e)


# =============================================================================
# FORGOT PASSWORD — public, sends Brevo reset email
# =============================================================================


@auth_router.post(
    "/password/forgot",
    auth=None,
    response={200: MessageResponseSchema, 404: ErrorResponseSchema},
    summary="Request password reset email",
    description="""
    Send a password-reset email to the given address.

    Returns 404 if the email is not associated with any active account —
    this platform is internal and enumeration is not a concern.
    The reset link is valid for **30 minutes** and can only be used once.
    A new request voids all previous unused links for the same account.
    """,
)
def forgot_password(request, data: ForgotPasswordSchema):
    try:
        AuthService.request_password_reset(data.email)
        return MessageResponseSchema(
            message="A password-set link has been sent to your email.",
            success=True,
        )
    except AuthenticationError as e:
        handle_auth_error(e)


# =============================================================================
# VALIDATE RESET TOKEN — public, called on page load before showing form
# =============================================================================


@auth_router.get(
    "/password/reset/validate",
    auth=None,
    response={200: MessageResponseSchema},
    summary="Check whether a reset token is still valid",
    description="Returns success=true if the token exists, is unused, and has not expired. No state is changed.",
)
def validate_reset_token(request, token: str):
    result = AuthService.validate_reset_token(token)
    return MessageResponseSchema(message=result["reason"], success=result["valid"])


# =============================================================================
# RESET PASSWORD — public, consumes token from email link
# =============================================================================


@auth_router.post(
    "/password/reset",
    auth=None,
    response={200: MessageResponseSchema, 400: ErrorResponseSchema},
    summary="Reset password with token",
    description="""
    Set a new password using the token received by email.

    The token is single-use and expires after 30 minutes.
    """,
)
def reset_password(request, data: ResetPasswordSchema):
    try:
        AuthService.reset_password(data.token, data.new_password)
        return MessageResponseSchema(message="Password reset successfully.", success=True)
    except AuthenticationError as e:
        handle_auth_error(e)


# =============================================================================
# SET PASSWORD — JWT-protected, for Hasura-synced users with no password yet
# =============================================================================


@auth_router.post(
    "/password/set",
    auth=jwt_auth,
    response={200: MessageResponseSchema, 400: ErrorResponseSchema},
    summary="Set password for first time (Hasura-synced users)",
    description="""
    Set a password for an account that was created via Hasura sync and has no
    password auth yet. Requires a valid JWT (user must be logged in via Google
    or a temp token issued during first-time setup).
    """,
)
def set_password(request, data: SetPasswordSchema):
    from sessionops.models import User

    user_id = getattr(request, "user", None)
    if not user_id or not hasattr(user_id, "email"):
        raise HttpError(401, "User not found")

    try:
        user = User.objects.get(email=user_id.email)
    except User.DoesNotExist:
        raise HttpError(401, "User not found")

    try:
        AuthService.set_password_first_time(user, data.new_password)
        return MessageResponseSchema(message="Password set successfully.", success=True)
    except AuthenticationError as e:
        handle_auth_error(e)


# =============================================================================
# PERMISSIONS CHECK — scoped per-school, used by frontend to gate CRUD buttons
# =============================================================================


@auth_router.get(
    "/me/permissions/",
    auth=jwt_auth,
    response={200: PermissionsResponseSchema, 401: ErrorResponseSchema, 404: ErrorResponseSchema},
    summary="Get caller's permissions for a school",
    description="Returns can_view and can_modify booleans for the given school_id.",
)
def get_my_permissions(request, school_id: int):
    from sessionops.exceptions import NotFound
    from sessionops.models import Partner, User
    from sessionops.services.rbac.scope import can_modify_school, can_view_school

    user_id = getattr(request, "user", None)
    if not user_id or not hasattr(user_id, "email"):
        raise HttpError(401, "User not found")
    try:
        caller = User.objects.get(email=user_id.email)
    except User.DoesNotExist:
        raise HttpError(401, "User not found")

    try:
        partner = Partner.objects.get(partner_id=school_id)
    except Partner.DoesNotExist:
        raise NotFound(f"School {school_id} not found.")

    from sessionops.services.progression.freeze import is_school_frozen

    frozen = is_school_frozen(school_id)  # F-M10-5: read-only while progressing
    return PermissionsResponseSchema(
        can_view=can_view_school(caller, partner),
        can_modify=can_modify_school(caller, partner) and not frozen,
    )
