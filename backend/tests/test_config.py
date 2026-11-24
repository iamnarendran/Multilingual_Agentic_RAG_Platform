"""Settings validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import DEV_JWT_SECRET, Settings


def test_blank_jwt_secret_falls_back_to_dev_secret_outside_production():
    assert Settings(jwt_secret="", _env_file=None).jwt_secret == DEV_JWT_SECRET


@pytest.mark.parametrize("secret", ["", "   ", DEV_JWT_SECRET, "too-short"])
def test_production_requires_a_real_jwt_secret(secret: str):
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(environment="production", jwt_secret=secret, _env_file=None)


def test_production_accepts_strong_secret_and_per_agent_models():
    s = Settings(environment="production", jwt_secret="a" * 64, planner_model="google/x", _env_file=None)
    assert s.model_for("planner") == "google/x"
    assert s.model_for("router") == s.llm_fast_model
    assert s.model_for("generator") == s.llm_model


def test_chunk_overlap_must_be_smaller_than_chunk_size():
    with pytest.raises(ValidationError, match="CHUNK_OVERLAP"):
        Settings(chunk_size=100, chunk_overlap=100, _env_file=None)
