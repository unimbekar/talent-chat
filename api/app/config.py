"""Environment settings. Copy defaults live here, not in business logic."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root() -> Path:
    # api/app/config.py -> parents: app, api, repo
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "configs" / "locations.yaml").exists():
            return parent
    return here.parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://app_admin:admin@127.0.0.1:5432/talent"
    database_public_url: str = "postgresql+psycopg://app_public:public@127.0.0.1:5432/talent"
    database_migrate_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/talent"
    app_admin_db_password: str = "admin"
    app_public_db_password: str = "public"

    admin_password_hash: str = ""
    admin_password_hash_file: str = ""
    session_secret: str = "dev-session-secret-change-me"
    session_secure: bool = False

    company_name: str = "Janus Soft Inc."
    careers_url: str = "https://www.janus-soft.com/career"
    # Branding for a customer deployment. The web app reads these from GET /public/config.
    brand_tagline: str = "Find the role that fits you"
    brand_accent: str = "#857251"
    brand_logo_url: str = "/brand/mark.jpg"
    brand_hero_url: str = "/brand/hero.jpg"
    brand_footer: str = (
        "This tool is not authorized for classified processing and is not a FedRAMP system; "
        "do not upload classified documents or CUI."
    )
    chat_examples: str = "Which jobs require Spring Boot?|Java and AWS jobs|Jobs in Chantilly|Do any roles need a clearance?"
    company_email_domain: str = "janus-soft.com"
    resume_library_host: str = "/mnt/synology/janus-soft"
    crawl_interval_hours: float = 6
    crawl_on_start: bool = False
    warm_resume_cache: bool = True
    crawl_request_delay_seconds: float = 1.0
    public_frame_ancestor: str = ""
    trusted_proxy_header: str = ""

    llm_backend: str = "openai_compat"
    llm_base_url: str = "http://host.docker.internal:11434/v1"
    llm_model: str = "qwen3.6:latest"
    llm_api_key: str = ""
    # Sent as reasoning_effort to openai_compat servers. "none" turns Qwen3 thinking off on
    # Ollama. Set it empty for servers that reject the field.
    llm_reasoning_effort: str = "none"
    aws_region: str = "us-east-1"
    # Recruiter assistant. An empty model means the assistant uses LLM_MODEL. The backend can
    # differ, for example the assistant on Bedrock while extraction stays on the DGX.
    assistant_backend: str = ""
    assistant_model: str = ""
    assistant_max_steps: int = 5

    embedding_model: str = "nomic-ai/nomic-embed-text-v1.5"
    file_dir: str = "./data/uploads"
    s3_bucket: str = ""
    s3_ingest_prefix: str = "inbox"
    public_base_url: str = "http://localhost:3010"
    google_client_id: str = ""
    google_client_secret: str = ""
    resume_folder: str = ""
    locations_file: str = ""

    def resolved_admin_hash(self) -> str:
        if self.admin_password_hash_file:
            path = Path(self.admin_password_hash_file)
            if path.exists():
                return path.read_text(encoding="utf-8").strip()
        return self.admin_password_hash.strip()

    def locations_path(self) -> Path:
        if self.locations_file:
            return Path(self.locations_file)
        return _repo_root() / "configs" / "locations.yaml"


@lru_cache
def get_settings() -> Settings:
    return Settings()
