from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_TARGET = "CyaE1VxvBrahnPWkqm5VsdCvyS2QmNht2UFrKJHga54o"
DEFAULT_PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    helius_api_key: str = Field(alias="HELIUS_API_KEY")
    target_wallet: str = Field(default=DEFAULT_TARGET, alias="TARGET_WALLET")
    pump_program_id: str = Field(default=DEFAULT_PUMP_PROGRAM, alias="PUMP_PROGRAM_ID")
    helius_wss_url: str = Field(
        default="wss://mainnet.helius-rpc.com/?api-key={api_key}", alias="HELIUS_WSS_URL"
    )
    commitment: str = Field(default="processed", alias="COMMITMENT")
    data_dir: Path = Field(default=Path("./data"), alias="DATA_DIR")
    flush_every: int = Field(default=25, alias="FLUSH_EVERY", ge=1)
    reconnect_max_seconds: int = Field(default=30, alias="RECONNECT_MAX_SECONDS", ge=1)
    include_failed: bool = Field(default=False, alias="INCLUDE_FAILED")

    @field_validator("helius_api_key")
    @classmethod
    def api_key_not_placeholder(cls, value: str) -> str:
        if not value or value == "replace_me":
            raise ValueError("Set HELIUS_API_KEY in .env before running the live collector")
        return value

    @field_validator("commitment")
    @classmethod
    def valid_commitment(cls, value: str) -> str:
        allowed = {"processed", "confirmed", "finalized"}
        if value not in allowed:
            raise ValueError(f"COMMITMENT must be one of {sorted(allowed)}")
        return value

    @property
    def websocket_url(self) -> str:
        return self.helius_wss_url.format(api_key=self.helius_api_key)
