"""Index generation contracts."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from .documents import StrictModel

GenerationState = Literal["building", "validating", "active", "failed", "cancelled", "retired"]
QualityState = Literal["pending", "passed", "failed"]


class IndexGeneration(StrictModel):
    generation_id: str = Field(min_length=1, max_length=64)
    run_id: str = Field(min_length=1, max_length=64)
    store_id: str = Field(min_length=1, max_length=64)
    state: GenerationState = "building"
    quality_state: QualityState = "pending"
    ontology_version: str = Field(min_length=1, max_length=50)
    extractor_version: str = Field(min_length=1, max_length=50)
    embedding_dimensions: int = Field(gt=0)
