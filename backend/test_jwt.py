from app.services.jwt_service import JWTService

jwt_service = JWTService()

access = jwt_service.create_access_token(
    user_id="123456",
    email="test@example.com",
)

refresh = jwt_service.create_refresh_token(
    user_id="123456",
    email="test@example.com",
)

print("\nACCESS TOKEN\n")
print(access)

print("\nREFRESH TOKEN\n")
print(refresh)

print("\nDECODE ACCESS\n")
print(jwt_service.verify_access_token(access))

print("\nDECODE REFRESH\n")
print(jwt_service.verify_refresh_token(refresh))