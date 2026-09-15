from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5"
    fhir_base_url: str = "http://localhost:8080/fhir"
    db_path: str = "./data/prior_auth.db"
    chroma_path: str = "./data/chroma"
    rules_path: str = "rules/prior_auth_rules.yaml"


settings = Settings()
