"""Gemini API calls and quota/retry handling for per-paper extraction."""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from .. import config
from .prompts import (
    _DETAIL_EXTRACTION_CRITICAL_INSTRUCTIONS,
    _GENE_DISCOVERY_INSTRUCTION_ABSTRACT,
    _GENE_DISCOVERY_INSTRUCTION_FULLTEXT,
)


class GeminiClientMixin:
    @staticmethod
    def _is_rate_limit_error(error: Exception) -> bool:
        err = str(error)
        return "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower()

    @staticmethod
    def _extract_retry_delay_seconds(error: Exception) -> Optional[int]:
        err = str(error)
        delay_match = re.search(r"retryDelay[\"'\s:]+(\d+)s", err)
        if delay_match:
            return int(delay_match.group(1))
        return None

    def _can_make_gemini_call(
        self,
        purpose: str,
        *,
        optional: bool = False,
        reserved_required_calls: int = 0,
    ) -> bool:
        max_calls = int(getattr(config, "GEMINI_MAX_CALLS_PER_PAPER", 0) or 0)
        if optional and max_calls > 0 and reserved_required_calls > 0:
            optional_slots = max_calls - self._paper_api_calls - reserved_required_calls
            if optional_slots <= 0:
                logging.info(
                    "Gemini call budget preserving "
                    f"{reserved_required_calls} required call(s) for this paper "
                    f"({self._paper_api_calls}/{max_calls}); skipping optional {purpose}"
                )
                return False
        if max_calls <= 0 or self._paper_api_calls < max_calls:
            return True
        msg = (
            f"Gemini call budget reached for this paper "
            f"({self._paper_api_calls}/{max_calls}); skipping {purpose}"
        )
        if optional:
            logging.info(msg)
            return False
        raise RuntimeError(msg)

    def _generate_content_text(
        self,
        *,
        model_name: str,
        contents: list,
        generate_content_config: Any,
        purpose: str,
        optional: bool = False,
        reserved_required_calls: int = 0,
    ) -> str:
        """Call Gemini with per-paper budget and spacing guards."""
        if not self._can_make_gemini_call(
            purpose,
            optional=optional,
            reserved_required_calls=reserved_required_calls,
        ):
            return ""

        min_delay = float(getattr(config, "GEMINI_INTER_CALL_DELAY_SECONDS", 0) or 0)
        if self._last_gemini_call_at is not None and min_delay > 0:
            elapsed = time.time() - self._last_gemini_call_at
            if elapsed < min_delay:
                time.sleep(min_delay - elapsed)

        self._paper_api_calls += 1
        self._last_gemini_call_at = time.time()
        full_response_text = ""
        try:
            for chunk in self.client.models.generate_content_stream(
                model=f"models/{model_name}",
                contents=contents,
                config=generate_content_config,
            ):
                if chunk.text:
                    full_response_text += chunk.text
        except Exception as e:
            if self._is_rate_limit_error(e):
                self._quota_limited = True
            raise
        return full_response_text

    def _should_retry_gemini_error(self, error: Exception, attempt: int, max_retries: int) -> tuple[bool, int]:
        """Return (should_retry, wait_seconds) for Gemini failures."""
        if attempt >= max_retries - 1:
            return False, 0

        if not self._is_rate_limit_error(error):
            wait = 2 ** attempt
            return True, max(1, wait)

        suggested = self._extract_retry_delay_seconds(error)
        if suggested is None:
            return False, 0
        if not getattr(config, "GEMINI_RETRY_RATE_LIMIT_WITH_DELAY", True):
            return False, 0
        wait = min(
            int(suggested) + 3,
            int(getattr(config, "GEMINI_MAX_RATE_LIMIT_WAIT_SECONDS", 75)),
        )
        return True, max(wait, 1)

    def _format_table_summary_for_prompt(self) -> str:
        """Format structured tables as a compact prompt section for Gemini.

        Caps at TABLE_MAX_PER_PAPER tables, 20 rows per table to avoid context overflow.
        """
        parts = []
        for t in self.table_inputs[:getattr(config, 'TABLE_MAX_PER_PAPER', 20)]:
            label = t.get("label", "Table")
            caption = t.get("caption", "")
            headers = t.get("headers", [])
            rows = t.get("rows", [])[:20]
            header_str = " | ".join(headers) if headers else ""
            row_strs = [" | ".join(str(c) for c in r) for r in rows]
            table_block = f"[{label}] {caption}"
            if header_str:
                table_block += f"\n{header_str}"
            if row_strs:
                table_block += "\n" + "\n".join(row_strs)
            parts.append(table_block)
        return "\n\n".join(parts)

    def extract_gene_names_from_abstract(self, title: str = ""):
        """
        FIX #5 (Revised): Extract gene-variant associations from ABSTRACT ONLY.

        This saves 99%+ tokens compared to full-text extraction for gene discovery.
        Typical abstract: 200-300 tokens vs. full text: 50,000+ tokens.

        Args:
            title: Paper title (optional, helps with context)

        Returns:
            List of gene-variant associations found in abstract
        """
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        if not self.abstract_text or len(self.abstract_text) < 50:
            logging.warning("Abstract too short or missing for gene extraction")
            return []

        model_name = config.GEMINI_CONFIG["gene_extraction_model"]  # Flash model

        # Combine title + abstract for better context
        text_to_analyze = (
            f"Title: {title}\n\nAbstract: {self.abstract_text}" if title else self.abstract_text
        )

        generate_content_config = types.GenerateContentConfig(
            temperature=config.GEMINI_CONFIG["temperature"],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            response_mime_type="application/json",
            response_schema=genai.types.Schema(
                type=genai.types.Type.OBJECT,
                required=["associations"],
                properties={
                    "associations": genai.types.Schema(
                        type=genai.types.Type.ARRAY,
                        items=genai.types.Schema(
                            type=genai.types.Type.OBJECT,
                            properties={
                                "gene": genai.types.Schema(
                                    type=genai.types.Type.STRING,
                                    description="Official HGNC gene symbol (e.g. IL6, CXCL9, BRCA1)",
                                ),
                                "variant": genai.types.Schema(
                                    type=genai.types.Type.STRING,
                                    description="Specific variant if mentioned (e.g. rs1234, c.123A>G), or empty string if none",
                                ),
                            },
                        ),
                    ),
                },
            ),
        )

        instruction = _GENE_DISCOVERY_INSTRUCTION_ABSTRACT

        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"{instruction}\n\n{text_to_analyze}")],
            ),
        ]

        max_retries = max(1, int(getattr(config, "GEMINI_OPTIONAL_MAX_RETRIES", 1)))

        for attempt in range(max_retries):
            try:
                full_response_text = self._generate_content_text(
                    model_name=model_name,
                    contents=contents,
                    generate_content_config=generate_content_config,
                    purpose="abstract gene discovery",
                    optional=True,
                    reserved_required_calls=2,
                )
                if not full_response_text:
                    break

                response_json = json.loads(full_response_text)
                self.associations = response_json.get("associations", [])

                if self.associations:
                    logging.info(
                        f"Abstract gene discovery found {len(self.associations)} associations"
                    )
                else:
                    logging.info(
                        "Abstract gene discovery found no associations"
                    )

                break  # Success

            except Exception as e:
                logging.error(
                    f"Error during abstract gene extraction (attempt {attempt + 1}/{max_retries}): {e}"
                )
                should_retry, wait = self._should_retry_gemini_error(e, attempt, max_retries)
                if should_retry:
                    time.sleep(wait)
                else:
                    logging.error("Abstract gene extraction failed after all retries")
                    self.associations = []
                    break

        return self.associations

    def extract_gene_names(self, temperature: float = None, *, optional: bool = True):
        """
        Extract gene-variant associations from the paper text using Gemini AI.

        If PubTator genes were provided (hybrid pipeline), they are used as high-confidence
        seeds that the LLM should include and can find additional genes beyond.

        Args:
            temperature: Override sampling temperature. If None, uses config default.
                         Pass a non-zero value (e.g. 0.4) for a recall-boosting second pass
                         so the model explores different completions instead of repeating pass 1.
            optional: If False, failures raise so the caller can fail paper analysis.
        """
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        model_name = config.GEMINI_CONFIG["gene_extraction_model"]
        effective_temperature = (
            temperature if temperature is not None else config.GEMINI_CONFIG["temperature"]
        )

        # Build instruction + paper text
        instruction = _GENE_DISCOVERY_INSTRUCTION_FULLTEXT

        if self.pubtator_genes:
            # Hybrid mode: PubTator found these genes with high confidence
            pt_genes_str = ", ".join(self.pubtator_genes[:20])  # Limit to avoid context overflow
            user_prompt = f"""{instruction}

The following genes have been identified with high confidence by PubTator NER: {pt_genes_str}
Make sure to include these genes in your output. Additionally, look for any other genes that PubTator may have missed.

Paper text:
{self.paper_text}"""
            logging.info(
                f"Hybrid mode: Seeding Gemini with {len(self.pubtator_genes)} PubTator genes"
            )
        else:
            user_prompt = f"{instruction}\n\nPaper text:\n{self.paper_text}"

        generate_content_config = types.GenerateContentConfig(
            temperature=effective_temperature,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            response_mime_type="application/json",
            response_schema=genai.types.Schema(
                type=genai.types.Type.OBJECT,
                required=["associations"],
                properties={
                    "associations": genai.types.Schema(
                        type=genai.types.Type.ARRAY,
                        items=genai.types.Schema(
                            type=genai.types.Type.OBJECT,
                            properties={
                                "gene": genai.types.Schema(
                                    type=genai.types.Type.STRING,
                                    description="Official HGNC gene symbol (e.g. IL6, CXCL9, BRCA1, TP53)",
                                ),
                                "variant": genai.types.Schema(
                                    type=genai.types.Type.STRING,
                                    description="Specific variant if mentioned (e.g. rs1234, c.123A>G), or empty string if none",
                                ),
                            },
                        ),
                    ),
                },
            ),
        )

        contents = [
            types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)]),
        ]

        retry_config_name = "GEMINI_OPTIONAL_MAX_RETRIES" if optional else "GEMINI_MAX_RETRIES"
        max_retries = max(1, int(getattr(config, retry_config_name, 1)))

        for attempt in range(max_retries):
            try:
                full_response_text = self._generate_content_text(
                    model_name=model_name,
                    contents=contents,
                    generate_content_config=generate_content_config,
                    purpose="full-text gene discovery",
                    optional=optional,
                    reserved_required_calls=1 if optional else 0,
                )
                if not full_response_text:
                    if not optional:
                        raise RuntimeError("full-text gene discovery returned an empty response")
                    break

                response_json = json.loads(full_response_text)
                if not isinstance(response_json, dict):
                    raise ValueError("full-text gene discovery response was not a JSON object")
                if "associations" not in response_json:
                    raise ValueError(
                        "full-text gene discovery response missing required 'associations' field"
                    )
                parsed_associations = response_json.get("associations", [])
                if parsed_associations is None:
                    parsed_associations = []
                if not isinstance(parsed_associations, list):
                    raise ValueError(
                        "full-text gene discovery response field 'associations' was not a list"
                    )
                if parsed_associations:
                    self._ingest_associations(parsed_associations, "llm_text")
                    break  # Success, exit retry loop

                if not optional:
                    logging.info("Mandatory full-text gene discovery returned no associations")
                    break

                # Empty association list is a known flaky model outcome; retry.
                if attempt < max_retries - 1:
                    logging.warning(
                        f"Gene extraction returned 0 associations (attempt {attempt + 1}/{max_retries}), retrying..."
                    )
                    time.sleep(2 ** attempt)
                    continue
                break

            except Exception as e:
                logging.error(
                    f"Error during gene-variant extraction (attempt {attempt + 1}/{max_retries}): {e}"
                )
                should_retry, wait = self._should_retry_gemini_error(e, attempt, max_retries)
                if should_retry:
                    logging.info(f"Retrying in {wait} seconds...")
                    time.sleep(wait)
                else:
                    logging.error("All retry attempts failed for gene-variant extraction")
                    if not optional:
                        raise RuntimeError(
                            "mandatory full-text gene discovery failed after "
                            f"{attempt + 1} attempt(s): {e}"
                        ) from e
                    break

        return self.associations

    def extract_gene_info(self, column_descriptions):
        """
        Extract detailed info for identified gene-variant associations based on provided column descriptions.
        """
        if not self.associations:
            self.detail_extraction_status = "no_associations"
            self.detail_extraction_error = ""
            self.detail_extraction_rows = 0
            return []

        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        model_name = config.GEMINI_CONFIG["data_extraction_model"]

        properties = {
            "gene_name": genai.types.Schema(
                type=genai.types.Type.STRING, description="The name of the gene."
            )
        }
        properties["variant_name"] = genai.types.Schema(
            type=genai.types.Type.STRING, description="The associated variant, if any."
        )
        # Only require identifiers; user fields are optional so the model can omit generic, non-variant-specific text
        required = ["gene_name", "variant_name"]
        # For each user column, request both the value and a separate citation field (optional)
        for column, description in column_descriptions.items():
            # Value field (optional)
            properties[column] = genai.types.Schema(
                type=genai.types.Type.STRING, description=description
            )
            # Citation field (optional)
            citation_col = f"{column} Citation"
            properties[citation_col] = genai.types.Schema(
                type=genai.types.Type.STRING,
                description=f"Direct quote or section/page reference supporting {column}. Leave empty if no variant-specific evidence.",
            )

        generate_content_config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            response_mime_type="application/json",
            response_schema=genai.types.Schema(
                type=genai.types.Type.ARRAY,
                items=genai.types.Schema(
                    type=genai.types.Type.OBJECT,
                    required=required,
                    properties=properties,
                ),
            ),
        )

        normalized_associations = []
        for assoc in self.associations:
            gene = (assoc.get("gene") or "").strip()
            variant = self._normalize_variant_value(assoc.get("variant", ""))
            if not gene:
                continue
            normalized_associations.append({"gene_name": gene, "variant_name": variant})

        associations_json = json.dumps(normalized_associations, ensure_ascii=False)
        prompt_text = (
            "Based on the following research paper text, extract the requested information for the following gene-variant associations:\n\n"
            f"Associations JSON (authoritative input): {associations_json}\n\n"
            "IMPORTANT: For each piece of information you extract, provide a specific citation "
            "(quote or section/page reference) from the paper text that directly supports your answer. "
            "If supporting evidence is not present, leave both the value and citation empty.\n\n"
            "Information to extract for each association:\n"
        )
        prompt_text += "- gene_name: The name of the gene. (Use exactly the gene name from the associations above)\n"
        prompt_text += "- variant_name: The associated variant, if any. (Use exactly the variant name from the associations above)\n"
        for column, description in column_descriptions.items():
            lower_column = column.lower()
            extra_guidance = ""
            if "statistical" in lower_column or "evidence" in lower_column:
                extra_guidance = (
                    " Include qualitative statistical language when exact p-values are absent, "
                    "such as significantly upregulated/downregulated, differentially expressed, "
                    "not significant, statistical cut-off, fold-change, figure/table references, "
                    "or pathway enrichment statements."
                )
            elif "conclusion" in lower_column:
                extra_guidance = (
                    " If the paper has no explicit gene-specific conclusion sentence, summarize "
                    "the authors' supported interpretation from Results or Discussion for this gene."
                )
            prompt_text += f"- {column}: {description}. In the gene-only row (variant_name empty), provide gene-level facts that apply regardless of variant. In variant rows, include only variant-specific details; if none, leave empty.{extra_guidance}\n"
            prompt_text += f"- {column} Citation: Direct quote or section/page reference supporting {column}. Empty if the field is empty.\n"
        prompt_text += f"\nPaper text:\n{self.paper_text}"
        if self.table_inputs and getattr(config, "ENABLE_TABLE_CITATIONS", True):
            prompt_text += f"\n\n--- STRUCTURED TABLE DATA ---\n{self._format_table_summary_for_prompt()}"

        prompt_text += _DETAIL_EXTRACTION_CRITICAL_INSTRUCTIONS

        contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt_text)])]

        max_retries = max(1, int(getattr(config, "GEMINI_MAX_RETRIES", 1)))

        for attempt in range(max_retries):
            try:
                full_response_text = self._generate_content_text(
                    model_name=model_name,
                    contents=contents,
                    generate_content_config=generate_content_config,
                    purpose="detail extraction",
                    optional=False,
                )

                parsed = json.loads(full_response_text)
                if isinstance(parsed, list):
                    for row in parsed:
                        if not isinstance(row, dict):
                            continue
                        row["variant_name"] = self._normalize_variant_value(
                            row.get("variant_name", "")
                        )
                        # Cleanup no-evidence placeholders so CSV stays clean.
                        for col in column_descriptions:
                            if col in row:
                                row[col] = self._normalize_empty_placeholder(row.get(col, ""))
                            citation_col = f"{col} Citation"
                            if citation_col in row:
                                row[citation_col] = self._normalize_empty_placeholder(
                                    row.get(citation_col, "")
                                )
                        # F11: Tag as LLM-sourced so the output CSV can
                        # distinguish real LLM content from fallback skeletons
                        # produced when Gemini fails (quota, timeout, malformed).
                        row["extraction_mode"] = "llm"
                    self.detail_extraction_status = (
                        "model_response_parsed" if parsed else "model_response_empty_rows"
                    )
                    self.detail_extraction_error = ""
                    self.detail_extraction_rows = len(parsed)
                return parsed

            except Exception as e:
                logging.error(
                    f"Error during gene info extraction (attempt {attempt + 1}/{max_retries}): {e}"
                )
                should_retry, wait = self._should_retry_gemini_error(e, attempt, max_retries)
                if should_retry:
                    logging.info(f"Retrying in {wait} seconds...")
                    time.sleep(wait)
                else:
                    logging.error("All retry attempts failed for gene info extraction")
                    self.detail_extraction_status = (
                        "quota_limited_fallback"
                        if self._is_rate_limit_error(e)
                        else "fallback_after_retries"
                    )
                    self.detail_extraction_error = str(e)
                    # Return minimal fallback with gene/variant only — no fabricated content.
                    # F11: every fallback row is tagged extraction_mode="skeleton" and carries
                    # the failure reason, so downstream code (confidence scoring, CSV output)
                    # can visibly downgrade these rows instead of presenting them like LLM rows.
                    err_msg = str(e)[:300]  # cap to keep CSV readable
                    fallback_data = []
                    for assoc in self.associations:
                        fallback_item = {
                            "gene_name": assoc["gene"],
                            "variant_name": self._normalize_variant_value(assoc.get("variant", "")),
                            "extraction_mode": "skeleton",
                            "detail_extraction_error": err_msg,
                        }
                        for col in column_descriptions:
                            fallback_item[col] = ""
                            fallback_item[f"{col} Citation"] = ""
                        fallback_data.append(fallback_item)
                    self.detail_extraction_rows = len(fallback_data)
                    return fallback_data
