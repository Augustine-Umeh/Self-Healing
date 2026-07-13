from pydantic_settings import BaseSettings, SettingsConfigDict  # pyright: ignore[reportMissingImports]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mefid_api_url: str
    observe_interval_seconds: int
    stuck_processing_minutes: int
    count_delta_tolerance: int

    supabase_url: str
    supabase_role_key: str
    supabase_admin_api_key: str

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_role_key and self.supabase_admin_api_key)


def get_settings() -> Settings:
    return Settings()