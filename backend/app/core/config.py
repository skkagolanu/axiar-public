import secrets
from typing import Any, List, Optional, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Axiar API"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    SECRET_KEY: SecretStr = Field(default_factory=lambda: SecretStr(secrets.token_urlsafe(32)))
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"

    # Database
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 50
    DATABASE_MAX_OVERFLOW: int = 50
    # Number of DB shards. 1 = single database (default). When >1, ShardRouter distributes
    # tenants across shards by consistent hashing; per-shard URLs come from
    # DATABASE_SHARD_<i>_URL or are derived from DATABASE_URL.
    DATABASE_SHARD_COUNT: int = 1

    # Redis
    REDIS_URL: str = ""
    REDIS_CLUSTER_NODES: str = ""

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = ""
    KAFKA_SECURITY_PROTOCOL: str = "PLAINTEXT"
    KAFKA_SASL_MECHANISM: str = "SCRAM-SHA-256"
    KAFKA_SASL_USERNAME: str = ""
    KAFKA_SASL_PASSWORD: SecretStr = SecretStr("")
    KAFKA_SSL_CA_CERT: SecretStr = SecretStr("")

    # AI Services
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    AI_MODEL: str = "llama3.1:8b"
    CHROMA_PERSIST_DIRECTORY: str = "./chroma_db"

    # External APIs
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    # Points the stripe-python SDK at a local stripe-mock server instead of the
    # real Stripe API. Empty in every real deployment (the SDK's own default
    # api_base applies); set only in CI's e2e-tests job so guest-payment E2E
    STRIPE_API_BASE: str = ""
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = "contact@example.test"
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    GOOGLE_MAPS_API_KEY: str = ""

    # OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    MICROSOFT_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_SECRET: str = ""

    # JWT
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Frontend
    FRONTEND_URL: str = "http://localhost:3000"
    API_BASE_URL: str = "http://localhost:8000"

    SESSION_SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    
    # It is now enabled by default for production readiness; set to "false" in your
    # .env or via the RATE_LIMIT_ENABLED env var to disable.
    RATE_LIMIT_ENABLED: bool = True
    # Only set behind a trusted proxy that overwrites this header. Render routes
    # public traffic through Cloudflare, which supplies CF-Connecting-IP.
    RATE_LIMIT_TRUSTED_PROXY_HEADER: str = ""

    # the demo data if the caller presents this token. Empty (default) = route 404s.
    DEMO_RESET_TOKEN: str = ""
    # create-intent skips Stripe entirely and /payments/demo-confirm replays the
    # webhook success path with a synthetic event. Off (default) = real Stripe.
    DEMO_MODE: bool = False
    DEMO_TENANT_SLUG: str = "demo"

    # Web Push (VAPID) — push notifications disabled unless both keys are set
    VAPID_PUBLIC_KEY: Optional[str] = None
    VAPID_PRIVATE_KEY: Optional[str] = None
    VAPID_SUBJECT: str = "mailto:contact@example.test"

    # Multi-tenancy
    DEFAULT_TENANT_ID: str = "default"
    TENANT_ISOLATION_LEVEL: str = "row_level"

    # Monitoring
    SENTRY_DSN: Optional[SecretStr] = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    PROMETHEUS_MULTIPROC_DIR: str = ""

    @field_validator("REDIS_CLUSTER_NODES", mode="before")
    @classmethod
    def parse_redis_nodes(cls, v: Any) -> Any:
        # Keep as string, will be split when used
        return v

    @field_validator("KAFKA_BOOTSTRAP_SERVERS", mode="before")
    @classmethod
    def parse_kafka_servers(cls, v: Any) -> Any:
        # Keep as string, will be split when used
        return v

    @field_validator("ALLOWED_HOSTS", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v: Any) -> Any:
        # Keep as string, will be split when used
        return v

    @model_validator(mode="after")
    def production_guard(self) -> Self:
        if self.ENVIRONMENT == "production":
            secret_value = self.SECRET_KEY.get_secret_value()
            if len(secret_value) < 32 or secret_value in ("CHANGE_ME", "changeme", "placeholder", "secret"):
                raise ValueError("SECRET_KEY must be at least 32 characters and not a known placeholder in production")
            if self.DEBUG:
                raise ValueError("DEBUG must be False in production mode")
            if "*" in (self.ALLOWED_HOSTS or "").split(","):
                raise ValueError("ALLOWED_HOSTS must not contain wildcard '*' in production mode")
            if "*" in (self.CORS_ORIGINS or "").split(","):
                raise ValueError("CORS_ORIGINS must not contain wildcard '*' in production mode")
            if not self.DEMO_MODE:
                required_integrations = {
                    "REDIS_URL": self.REDIS_URL,
                    "STRIPE_SECRET_KEY": self.STRIPE_SECRET_KEY,
                    "STRIPE_WEBHOOK_SECRET": self.STRIPE_WEBHOOK_SECRET,
                    "SENDGRID_API_KEY": self.SENDGRID_API_KEY,
                    "TWILIO_ACCOUNT_SID": self.TWILIO_ACCOUNT_SID,
                    "TWILIO_AUTH_TOKEN": self.TWILIO_AUTH_TOKEN,
                    "TWILIO_PHONE_NUMBER": self.TWILIO_PHONE_NUMBER,
                    "GOOGLE_MAPS_API_KEY": self.GOOGLE_MAPS_API_KEY,
                    "GOOGLE_CLIENT_ID": self.GOOGLE_CLIENT_ID,
                    "GOOGLE_CLIENT_SECRET": self.GOOGLE_CLIENT_SECRET,
                    "MICROSOFT_CLIENT_ID": self.MICROSOFT_CLIENT_ID,
                    "MICROSOFT_CLIENT_SECRET": self.MICROSOFT_CLIENT_SECRET,
                }
                missing = sorted(name for name, value in required_integrations.items() if not value)
                if missing:
                    raise ValueError(f"Missing production integration settings: {', '.join(missing)}")
        return self

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()  # env vars supplied at runtime
