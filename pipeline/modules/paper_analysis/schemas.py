"""Pydantic response schemas for Gemini-backed per-paper extraction."""

from typing import Any, Dict, List, Type

from pydantic import BaseModel, ConfigDict, Field, create_model


class CandidateAssociationResponse(BaseModel):
    reported_gene: str = Field(description="Official HGNC gene symbol when possible.")
    reported_variant: str = Field(
        default="",
        description="Specific variant if reported; empty string for gene-level findings.",
    )
    original_mention: str = Field(
        default="",
        description="Exact gene/protein/variant mention as written in the paper or figure.",
    )
    evidence_sentence: str = Field(
        default="",
        description="Concise source sentence or caption phrase containing the original mention.",
    )


class CandidateDiscoveryResponse(BaseModel):
    associations: List[CandidateAssociationResponse]


class DetailExtractionRowBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    gene_name: str = Field(description="The name of the gene.")
    variant_name: str = Field(description="The associated variant, if any.")


def _safe_detail_field_name(index: int, suffix: str = "") -> str:
    return f"user_field_{index}{suffix}"


def build_detail_extraction_response_model(
    column_descriptions: Dict[str, str],
) -> Type[BaseModel]:
    """Build a Pydantic response model for dynamic user-requested columns."""
    row_fields: Dict[str, Any] = {}
    for index, (column, description) in enumerate(column_descriptions.items()):
        row_fields[_safe_detail_field_name(index)] = (
            str,
            Field(default="", alias=column, description=description),
        )
        row_fields[_safe_detail_field_name(index, "_citation")] = (
            str,
            Field(
                default="",
                alias=f"{column} Citation",
                description=(
                    f"Direct quote or section/page reference supporting {column}. "
                    "Leave empty if no variant-specific evidence."
                ),
            ),
        )

    detail_row_model = create_model(
        "DetailExtractionRow",
        __base__=DetailExtractionRowBase,
        **row_fields,
    )
    return create_model(
        "DetailExtractionResponse",
        rows=(List[detail_row_model], Field(...)),  # type: ignore[valid-type]
    )
