"""Validation for the metadata accompanying an imported paper."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.knowledge.paths import RelativeTexPathError, validate_relative_tex_path


MAX_PAPER_ID_LENGTH = 128
MAX_TITLE_LENGTH = 512
MAX_COMPETITION_LENGTH = 128
MAX_PROBLEM_LENGTH = 64
MAX_AWARD_LENGTH = 128
MAX_LANGUAGE_LENGTH = 32
MAX_MAIN_TEX_LENGTH = 512
MAX_METHODS_PER_PAPER = 32
MAX_METHOD_LENGTH = 128


class PaperManifest(BaseModel):
    """Metadata declared by a paper's ``paper.yaml`` file."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    paper_id: str = Field(min_length=1, max_length=MAX_PAPER_ID_LENGTH)
    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH)
    competition: str = Field(min_length=1, max_length=MAX_COMPETITION_LENGTH)
    year: int = Field(ge=1900, le=2100)
    problem: str = Field(min_length=1, max_length=MAX_PROBLEM_LENGTH)
    award: str = Field(min_length=1, max_length=MAX_AWARD_LENGTH)
    language: str = Field(min_length=1, max_length=MAX_LANGUAGE_LENGTH)
    methods: list[str] = Field(default_factory=list, max_length=MAX_METHODS_PER_PAPER)
    main_tex: str = Field(min_length=1, max_length=MAX_MAIN_TEX_LENGTH)

    @field_validator("main_tex")
    @classmethod
    def main_tex_must_stay_inside_the_paper_root(cls, value: str) -> str:
        try:
            return validate_relative_tex_path(value, label="main_tex")
        except RelativeTexPathError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("methods")
    @classmethod
    def methods_must_be_nonempty_after_normalization(cls, values: list[str]) -> list[str]:
        normalized = [method.strip() for method in values]
        if any(not method for method in normalized):
            raise ValueError("methods cannot contain empty entries")
        if any(len(method) > MAX_METHOD_LENGTH for method in normalized):
            raise ValueError(f"methods entries cannot exceed {MAX_METHOD_LENGTH} characters")
        return normalized
