"""
환경 변수 / 설정 관리
.env 파일에서 자동 로드. 키가 없으면 mock 모드.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 서버 ──
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True

    # ── Provider 선택 ──
    bg_provider: str = "mock"
    text_provider: str = "mock"
    qc_provider: str = "mock"

    # ── 누끼 ──
    matting_model: str = "u2net"

    # ── 키 ──
    openai_api_key: str = ""
    stability_api_key: str = ""
    gemini_api_key: str = ""
    anthropic_api_key: str = ""

    # ── 저장소 ──
    workspace_dir: str = "./workspace"
    max_upload_mb: int = 20

    # ── 생성 ──
    default_variants: int = 4
    output_size: int = 1000

    # ── 백그라운드 작업 ──
    # 기본 False → 기존 스레드풀. True + celery 설치 + redis 가동 시 Celery 워커.
    use_celery: bool = False
    redis_url: str = "redis://localhost:6379/0"

    # ── 경로 헬퍼 ──
    @property
    def workspace_path(self) -> Path:
        p = (BASE_DIR / self.workspace_dir).resolve() if self.workspace_dir.startswith(".") else Path(self.workspace_dir)
        return p

    @property
    def uploads_path(self) -> Path:
        return self.workspace_path / "uploads"

    @property
    def outputs_path(self) -> Path:
        return self.workspace_path / "outputs"

    @property
    def temp_path(self) -> Path:
        return self.workspace_path / "temp"

    @property
    def jobs_path(self) -> Path:
        return self.workspace_path / "jobs"

    @property
    def feedback_path(self) -> Path:
        return self.workspace_path / "feedback"

    def ensure_dirs(self) -> None:
        for p in (self.uploads_path, self.outputs_path, self.temp_path,
                  self.jobs_path, self.feedback_path):
            p.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
