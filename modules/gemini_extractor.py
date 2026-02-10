import pandas as pd
import json
import logging
import re
from typing import Dict, Any, List, Optional

from . import config
from .gene_validator import (
    GeneValidator,
    validate_extracted_genes,
    ContextWindowValidator,
    validate_paper_context_fit,
)
from .gemini_rate_limiter import get_rate_limiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(module)s] - %(message)s",
)


def repair_json_response(text: str) -> str:
    """
    Attempt to repair truncated or malformed JSON responses.
    Handles common issues like unterminated strings, incomplete arrays, etc.
    """
    if not text.strip():
        return '{"associations": []}'

    text = text.strip()

    # Strategy 1: If we have unterminated strings, try to close them
    # Find the last position where we have a complete association entry
    # Pattern: {"gene": "...", "variant": "..."}
    # Look backwards from the end to find the last complete entry

    # Find all positions where we have complete association objects
    # More flexible pattern that handles whitespace
    pattern = r'\{\s*"gene"\s*:\s*"([^"]*)"\s*,\s*"variant"\s*:\s*"([^"]*)"\s*\}'
    matches = list(re.finditer(pattern, text))

    if matches:
        # Get text up to and including the last complete match
        last_match = matches[-1]
        # Find where "associations": [ starts
        associations_start = text.find('"associations"')
        if associations_start != -1:
            # Find the opening bracket after "associations"
            bracket_start = text.find("[", associations_start)
            if bracket_start != -1:
                # Use the original text up to the last complete match
                # This preserves the original structure and avoids duplication
                repaired = text[: last_match.end()]
                # Ensure it ends properly (remove trailing comma if any)
                repaired = repaired.rstrip().rstrip(",")
                # Close the array and object
                if not repaired.rstrip().endswith("]"):
                    repaired += "]"
                if not repaired.rstrip().endswith("}"):
                    repaired += "}"
                return repaired

    # Strategy 2: If text starts with { but doesn't end properly, try to close it
    if text.startswith("{") and '"associations"' in text:
        # Find the last complete association before truncation
        # Look for pattern: "gene": "value", "variant": "value"
        # Work backwards from the end
        last_complete_pos = -1
        for i in range(len(text) - 1, max(0, len(text) - 1000), -1):
            # Check if we have a complete association ending here
            # Look for closing brace followed by comma or closing bracket
            if text[i] == "}" and i > 0:
                # Check if this looks like end of an association object
                # Look backwards for "variant": "..."
                if '"variant"' in text[max(0, i - 200) : i + 1]:
                    last_complete_pos = i + 1
                    break

        if last_complete_pos > 0:
            repaired = text[:last_complete_pos]
            # Ensure it ends properly
            repaired = repaired.rstrip().rstrip(",")
            if not repaired.rstrip().endswith("]"):
                repaired += "]"
            if not repaired.rstrip().endswith("}"):
                repaired += "}"
            return repaired

    # Strategy 3: Simple closing if we have "associations": [ but incomplete
    if '"associations"' in text and "[" in text:
        # Remove any trailing incomplete content
        # Find the last complete entry by looking for closing braces
        text = text.rstrip().rstrip(",")
        # Count open vs closed braces/brackets
        open_braces = text.count("{") - text.count("}")
        open_brackets = text.count("[") - text.count("]")

        # Close brackets first, then braces
        if open_brackets > 0:
            text += "]" * open_brackets
        if open_braces > 0:
            text += "}" * open_braces

        return text

    # Last resort: return empty associations
    return '{"associations": []}'


def safe_json_loads(text: str, fallback: dict = None) -> dict:
    """
    Safely parse JSON with repair attempts.
    """
    if fallback is None:
        fallback = {"associations": []}

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logging.warning(f"JSON parse error: {e}. Attempting to repair...")
        logging.debug(f"Problematic JSON (first 500 chars): {text[:500]}")
        logging.debug(f"Problematic JSON (last 500 chars): {text[-500:]}")

        # Try to repair
        repaired = repair_json_response(text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as e2:
            logging.error(f"Repair failed: {e2}. Using fallback.")
            return fallback


class GeneInfoPipeline:
    def __init__(self, paper_text: str, abstract_text: str = ""):
        if not config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set in the configuration.")
        self.paper_text = paper_text
        self.abstract_text = abstract_text  # Store abstract separately
        self.original_paper_text = paper_text  # Keep original for reference
        self.associations = []
        self.validated_associations = []
        self.validation_results = []
        self.context_validation_results = {}
        # Lazy import to avoid top-level import failures
        from google import genai  # type: ignore

        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.gene_validator = GeneValidator()
        self.context_validator = ContextWindowValidator()

    def extract_gene_names_from_abstract(self, title: str = ""):
        """
        Extract gene-variant associations from abstract only.

        Uses minimal token consumption for initial gene discovery before
        full-text analysis. Typical abstract: 200-300 tokens.

        Args:
            title: Paper title (optional, provides additional context)

        Returns:
            List of gene-variant associations found in abstract
        """
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        if not self.abstract_text or len(self.abstract_text) < 50:
            logging.warning("Abstract too short or missing for gene extraction")
            return []

        model_name = config.GEMINI_CONFIG["gene_extraction_model"]  # Flash-Lite model

        # Combine title + abstract for better context
        text_to_analyze = (
            f"Title: {title}\n\nAbstract: {self.abstract_text}"
            if title
            else self.abstract_text
        )

        # Apply rate limiting before API call
        rate_limiter = get_rate_limiter()
        # Estimate tokens: ~0.75 tokens per word
        estimated_tokens = int(len(text_to_analyze.split()) * 0.75)
        rate_limiter.wait_if_needed(model_name, estimated_tokens)

        generate_content_config = types.GenerateContentConfig(
            temperature=config.GEMINI_CONFIG["temperature"],
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
                                    type=genai.types.Type.STRING
                                ),
                                "variant": genai.types.Schema(
                                    type=genai.types.Type.STRING
                                ),
                            },
                        ),
                    ),
                },
            ),
        )

        contents = [
            types.Content(
                role="user", parts=[types.Part.from_text(text=text_to_analyze)]
            ),
            # Seed the response format
            types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text="""{\"associations\": [{\"gene\": \"BRCA1\", \"variant\": \"c.123A>G\"}, {\"gene\": \"TP53\", \"variant\": \"p.Val600Glu\"}]}"""
                    )
                ],
            ),
        ]

        full_response_text = ""

        try:
            for chunk in self.client.models.generate_content_stream(
                model=f"models/{model_name}",
                contents=contents,
                config=generate_content_config,
            ):
                if chunk.text:
                    full_response_text += chunk.text

            response_json = json.loads(full_response_text)
            self.associations = response_json.get("associations", [])

            if self.associations:
                logging.info(
                    f"Abstract gene discovery found {len(self.associations)} associations"
                )
            else:
                logging.info(
                    "Abstract gene discovery found no associations - skipping full-text analysis"
                )

        except Exception as e:
            error_str = str(e)
            is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str

            if is_rate_limit:
                logging.warning(f"Rate limit hit during abstract gene extraction: {e}")
                logging.warning(
                    "Skipping retries to preserve quota - proceeding to full-text analysis"
                )
            else:
                logging.error(f"Error during abstract gene extraction: {e}")
                logging.warning("Skipping retries - proceeding to full-text analysis")

            self.associations = []

        return self.associations

    def extract_gene_names(self):
        """
        Extract gene-variant associations from the paper text using Gemini AI.
        """
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        model_name = config.GEMINI_CONFIG["gene_extraction_model"]

        generate_content_config = types.GenerateContentConfig(
            temperature=config.GEMINI_CONFIG["temperature"],
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
                                    type=genai.types.Type.STRING
                                ),
                                "variant": genai.types.Schema(
                                    type=genai.types.Type.STRING
                                ),
                            },
                        ),
                    ),
                },
            ),
        )

        # General, domain-agnostic extraction prompt with format specifications
        extraction_instructions = """Extract all gene-variant associations from this research paper.



Your task is to comprehensively identify all human genes and genetic variants mentioned in relation to the disease, condition, or phenotype being studied. Extract genes regardless of where they appear in the paper or how they are presented.



IMPORTANT: Format requirements:

- Genes: Extract only human genes. Use official HGNC (HUGO Gene Nomenclature Committee) gene symbols (e.g., "BRCA1", "TP53", "IL6"). If a gene is mentioned with an alternative name or alias, extract the official HGNC symbol if you can identify it.

- Variants: Extract genetic variants in standard HGVS (Human Genome Variation Society) notation where possible (e.g., "c.123A>G", "p.Val600Glu", "rs123456"). If the paper uses alternative notation, extract it as written but prefer HGVS format when identifiable.



IMPORTANT: Be thorough and exhaustive in your extraction:

- Extract genes mentioned anywhere in the paper: main text, tables, figures, supplementary materials, methods, results, and discussion sections

- Include genes from structured data formats (lists, tables, annotations, databases)

- Extract genes from both explicit associations and implicit mentions (e.g., pathway discussions, enrichment analyses)

- When encountering gene lists or enumerations, extract ALL genes from the list, not just a subset

- Include genes mentioned in technical contexts (statistics, methods, data tables) if they relate to the research topic



CRITICAL: Your goal is comprehensive documentation. Extract any human gene that is mentioned in the context of the disease/condition being studied, regardless of presentation format or section location. Use standardized nomenclature (HGNC for genes, HGVS for variants) when possible.



Paper text:

"""

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=extraction_instructions + self.paper_text)
                ],
            ),
            # Seed the response format with a concrete example like the working pipeline
            types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text="""{\"associations\": [{\"gene\": \"BRCA1\", \"variant\": \"c.123A>G\"}, {\"gene\": \"TP53\", \"variant\": \"p.Val600Glu\"}, {\"gene\": \"SELPLG\", \"variant\": \"\"}, {\"gene\": \"ITK\", \"variant\": \"\"}]}"""
                    )
                ],
            ),
        ]

        full_response_text = ""

        try:
            for chunk in self.client.models.generate_content_stream(
                model=f"models/{model_name}",
                contents=contents,
                config=generate_content_config,
            ):
                if chunk.text:
                    full_response_text += chunk.text

            # Use safe JSON parsing with repair logic
            response_json = safe_json_loads(full_response_text)
            raw_associations = response_json.get("associations", [])

            # Deduplicate associations (gene + variant combination)
            seen = set()
            deduplicated = []
            for assoc in raw_associations:
                if not isinstance(assoc, dict):
                    continue
                gene = (assoc.get("gene") or "").strip().upper()
                variant = (assoc.get("variant") or "").strip()
                key = (gene, variant)
                if key not in seen and gene:  # Only add if gene is non-empty
                    seen.add(key)
                    deduplicated.append(assoc)

            self.associations = deduplicated

            if self.associations:
                logging.info(
                    f"Successfully extracted {len(self.associations)} gene associations (after deduplication)"
                )
                if len(raw_associations) != len(deduplicated):
                    logging.info(
                        f"  Removed {len(raw_associations) - len(deduplicated)} duplicate associations"
                    )
                # Log warning if unusually high number of associations
                if len(self.associations) > 100:
                    logging.warning(
                        f"⚠️  Unusually high number of associations ({len(self.associations)}). "
                        f"This may indicate: (1) Large transcriptomics study, (2) Model extraction error. "
                        f"First 5 genes: {[a.get('gene', 'N/A') for a in self.associations[:5]]}"
                    )

        except json.JSONDecodeError as e:
            # Try repair once, but don't retry API call
            logging.error(f"JSON decode error during gene-variant extraction: {e}")
            logging.debug(f"Response length: {len(full_response_text)} chars")
            logging.debug(f"Response preview: {full_response_text[:200]}...")

            try:
                repaired = repair_json_response(full_response_text)
                response_json = json.loads(repaired)
                self.associations = response_json.get("associations", [])
                logging.info(
                    f"Repaired JSON and extracted {len(self.associations)} associations"
                )
            except Exception as e2:
                logging.error(f"Repair attempt failed: {e2}")
                logging.warning(
                    "Gemini API call failed - keeping empty associations, moving to next paper"
                )
                self.associations = []

        except Exception as e:
            error_str = str(e)
            is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str

            if is_rate_limit:
                logging.warning(f"Rate limit hit during gene-variant extraction: {e}")
                logging.warning(
                    "Skipping retries to preserve quota - moving to next paper"
                )
            else:
                logging.error(f"Error during gene-variant extraction: {e}")
                logging.warning(
                    "Skipping retries - keeping any data collected, moving to next paper"
                )

            self.associations = []

        return self.associations

    def extract_gene_info(self, column_descriptions):
        """
        Extract detailed info for identified gene-variant associations based on provided column descriptions.

        If there are many associations (> GENE_BATCH_THRESHOLD), processes them in batches
        to avoid API overload and improve reliability.
        """
        if not self.associations:
            return []

        # Get batch threshold from config (default: 8 genes per batch)
        batch_threshold = getattr(config, "GENE_BATCH_THRESHOLD", 8)
        total_associations = len(self.associations)

        # If we have many associations, process in batches
        if total_associations > batch_threshold:
            logging.info(
                f"Processing {total_associations} associations in batches of {batch_threshold} "
                f"(to avoid API overload)"
            )
            all_results = []

            # Split associations into batches
            for i in range(0, total_associations, batch_threshold):
                batch = self.associations[i : i + batch_threshold]
                batch_num = (i // batch_threshold) + 1
                total_batches = (
                    total_associations + batch_threshold - 1
                ) // batch_threshold

                logging.info(
                    f"Processing batch {batch_num}/{total_batches} ({len(batch)} associations)"
                )

                # Temporarily replace self.associations with batch
                original_associations = self.associations
                self.associations = batch

                try:
                    batch_results = self._extract_gene_info_single_batch(
                        column_descriptions
                    )
                    if batch_results:
                        all_results.extend(batch_results)
                except Exception as e:
                    logging.error(f"Batch {batch_num} failed: {e}")
                    # Fallback: add basic gene info for this batch
                    for assoc in batch:
                        fallback_item = {
                            "gene_name": assoc["gene"],
                            "variant_name": assoc.get("variant", "N/A"),
                        }
                        for col in column_descriptions:
                            fallback_item[col] = "N/A"
                            fallback_item[f"{col} Citation"] = ""
                        all_results.append(fallback_item)
                finally:
                    # Restore original associations
                    self.associations = original_associations

                # Small delay between batches to reduce API load
                if i + batch_threshold < total_associations:
                    import time

                    time.sleep(2)  # 2 second delay between batches

            logging.info(
                f"Completed batch processing: {len(all_results)} total results"
            )
            return all_results
        else:
            # Small number of associations - process normally
            return self._extract_gene_info_single_batch(column_descriptions)

    def _extract_gene_info_single_batch(self, column_descriptions):
        """
        Extract detailed info for a single batch of associations (internal method).
        """
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
                description=f"A complete, full sentence from the paper text that directly supports {column}. Must be a grammatically complete sentence (not a fragment). Leave empty if no supporting evidence exists.",
            )

        generate_content_config = types.GenerateContentConfig(
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

        associations_str = ", ".join(
            [
                f"{assoc['gene']} (variant: {assoc['variant'] or 'N/A'})"
                for assoc in self.associations
            ]
        )
        prompt_text = f"Based on the following research paper text, extract the requested information for the following gene-variant associations:\n\nAssociations: {associations_str}\n\nIMPORTANT: For each piece of information you extract, you MUST provide a specific citation (quote or page/section reference) from the paper text that directly supports your answer. If you cannot find supporting evidence in the paper, indicate 'No supporting citation found in paper'.\n\nInformation to extract for each association:\n"
        prompt_text += "- gene_name: The name of the gene. (Use exactly the gene name from the associations above)\n"
        prompt_text += "- variant_name: The associated variant, if any. (Use exactly the variant name from the associations above)\n"
        for column, description in column_descriptions.items():
            prompt_text += f"- {column}: {description}. In the gene-only row (variant_name empty), provide gene-level facts that apply regardless of variant. In variant rows, include only variant-specific details; if none, leave empty.\n"
            prompt_text += f"- {column} Citation: A complete, full sentence from the paper text that directly supports the {column} value. This must be a grammatically complete sentence (not a fragment or phrase). If no supporting evidence is found, leave this field empty.\n"
        prompt_text += f"\nPaper text:\n{self.paper_text}"

        prompt_text += "\n\nCRITICAL INSTRUCTIONS:"
        prompt_text += "\n- For gene_name and variant_name: Use exactly the names provided in the associations above."
        prompt_text += "\n- Always include one gene-only row per gene with variant_name empty. Put gene-level facts there."
        prompt_text += "\n- In variant rows, provide only variant-specific facts; if none, leave fields empty."
        prompt_text += "\n- Do not repeat the same generic sentence across multiple variants. Prefer leaving the variant rows blank rather than repeating gene-level text."
        prompt_text += "\n- For any field that is filled, provide a separate '{Field} Citation' as a COMPLETE, FULL SENTENCE from the paper (not a fragment). The citation must be grammatically complete and directly support the field value. Leave citation empty if no supporting evidence exists."
        prompt_text += "\n\nIMPORTANT: Extract information from ALL sections of the paper including:"
        prompt_text += "\n- Tables (especially supplementary tables with gene lists, pathway enrichment results, RNA-seq results)"
        prompt_text += "\n- Figure legends (genes mentioned in figure captions)"
        prompt_text += "\n- Methods sections (gene panels, gene lists)"
        prompt_text += "\n- Results sections (differentially expressed genes, pathway analysis results)"
        prompt_text += "\n- Even if genes appear in technical contexts (statistics, lists, tables), extract them if they relate to the disease/condition."
        model_name = config.GEMINI_CONFIG["data_extraction_model"]

        # Apply rate limiting before API call
        rate_limiter = get_rate_limiter()
        # Estimate tokens: prompt + paper text (~0.75 tokens per word)
        total_text = prompt_text + self.paper_text
        estimated_tokens = int(len(total_text.split()) * 0.75)
        rate_limiter.wait_if_needed(model_name, estimated_tokens)

        contents = [
            types.Content(role="user", parts=[types.Part.from_text(text=prompt_text)])
        ]

        full_response_text = ""

        try:
            for chunk in self.client.models.generate_content_stream(
                model=f"models/{model_name}",
                contents=contents,
                config=generate_content_config,
            ):
                if chunk.text:
                    full_response_text += chunk.text

            # Use safe JSON parsing with repair logic
            # Note: API returns an ARRAY directly (not wrapped in object)
            # So we parse JSON and ensure it's a list
            parsed = safe_json_loads(full_response_text, fallback=[])
            # Ensure we return a list (API schema is ARRAY, not OBJECT)
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict):
                # If somehow we got a dict (from fallback), return empty list
                logging.warning(
                    "Expected array but got dict from API response, returning empty list"
                )
                return []
            else:
                logging.warning(
                    f"Unexpected response type: {type(parsed)}, returning empty list"
                )
                return []

        except json.JSONDecodeError as e:
            # JSON decode error - try repair once, but don't retry API call
            logging.error(f"JSON decode error during gene info extraction: {e}")
            logging.debug(f"Response length: {len(full_response_text)} chars")
            try:
                repaired = repair_json_response(full_response_text)
                parsed = json.loads(repaired)
                # Ensure we return a list (API schema is ARRAY)
                if isinstance(parsed, list):
                    return parsed
                elif isinstance(parsed, dict) and "associations" in parsed:
                    # Handle case where response is wrapped in object
                    return parsed.get("associations", [])
                else:
                    logging.warning("Repaired JSON is not a list, using fallback")
                    raise ValueError("Invalid response structure")
            except Exception as e2:
                logging.error(f"Repair attempt failed: {e2}")
                logging.warning(
                    "Gemini API call failed - returning fallback data with basic gene info"
                )
                # Return fallback data with basic gene info (always a list)
                fallback_data = []
                for assoc in self.associations:
                    fallback_item = {
                        "gene_name": assoc["gene"],
                        "variant_name": assoc.get("variant", "N/A"),
                    }
                    for col in column_descriptions:
                        fallback_item[col] = "N/A"
                        fallback_item[f"{col} Citation"] = ""
                    fallback_data.append(fallback_item)
                return fallback_data

        except Exception as e:
            error_str = str(e)
            is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str

            if is_rate_limit:
                logging.warning(f"Rate limit hit during gene info extraction: {e}")
                logging.warning(
                    "Skipping retries to preserve quota - returning fallback data"
                )
            else:
                logging.error(f"Error during gene info extraction: {e}")
                logging.warning(
                    "Skipping retries - returning fallback data with basic gene info"
                )

            # Return fallback data instead of failing completely
            fallback_data = []
            for assoc in self.associations:
                fallback_item = {
                    "gene_name": assoc["gene"],
                    "variant_name": assoc.get("variant", "N/A"),
                }
                for col in column_descriptions:
                    fallback_item[col] = "N/A"
                    fallback_item[f"{col} Citation"] = ""
                fallback_data.append(fallback_item)
            return fallback_data

    def run_pipeline(self, column_descriptions, pre_discovered_associations=None):
        """
        Run extraction end-to-end and return a DataFrame with gene and citation validation heuristics.

        Args:
            column_descriptions: Dictionary of column names to descriptions for extraction
            pre_discovered_associations: Optional list of gene-variant associations already discovered
                                        (e.g., from abstract analysis). If provided and full-text extraction
                                        finds nothing, these will be used as fallback.
        """
        # Step 0: Validate and prepare paper text for context windows
        logging.info("Step 0: Validating paper text against model context limits")
        context_validation = self._validate_and_prepare_paper_text()

        if context_validation["failed"]:
            logging.error("Context validation failed - cannot proceed with pipeline")
            return pd.DataFrame()

        # Step 1: Extract gene names using smaller model
        logging.info("Step 1: Extracting gene-variant associations from paper text")
        self.extract_gene_names()

        # If full-text extraction found nothing but we have pre-discovered associations, use those as fallback
        if not self.associations and pre_discovered_associations:
            logging.info(
                f"Full-text extraction found no associations, using {len(pre_discovered_associations)} "
                f"pre-discovered associations from abstract analysis as fallback"
            )
            self.associations = pre_discovered_associations

        # First, ensure we have gene-level associations (variant empty) before validation
        try:
            existing_pairs = set()
            genes_present = set()
            normalized: List[Dict[str, str]] = []
            for assoc in self.associations:
                if isinstance(assoc, dict):
                    g = (assoc.get("gene") or "").strip()
                    v = assoc.get("variant") or ""
                else:
                    g, v = assoc
                g_up = g.strip().upper()
                v_norm = (v or "").strip()
                if isinstance(v_norm, str) and v_norm.upper() in {"N/A", "NA", "NONE"}:
                    v_norm = ""
                existing_pairs.add((g_up, v_norm))
                genes_present.add(g_up)
                normalized.append({"gene": g, "variant": v_norm})

            for g_up in genes_present:
                if (g_up, "") not in existing_pairs:
                    normalized.append({"gene": g_up, "variant": ""})

            self.associations = normalized
        except Exception as e:
            logging.debug(f"Failed to ensure gene-level associations: {e}")

        # Step 2: Apply heuristics to validate extracted genes (including gene-only rows)
        logging.info("Step 2: Validating extracted genes against known databases")
        self._apply_gene_validation_heuristics()

        # Step 3: Extract detailed info for validated associations using larger model
        logging.info(
            "Step 3: Extracting detailed information for validated associations"
        )
        extracted_info = self.extract_gene_info(column_descriptions)

        # Add validation metadata to results
        if extracted_info:
            df = pd.DataFrame(extracted_info)
            self._add_validation_metadata(df)

            # Only add citation validation if enabled
            if config.ENABLE_CITATION_VALIDATION:
                self._add_citation_validation_metadata(df)

            self._add_context_metadata(df, context_validation)
            return df

        return pd.DataFrame()

    def _apply_gene_validation_heuristics(self):
        """
        Apply heuristics to validate extracted gene-variant associations.

        Uses gene database validation to filter and improve accuracy.
        Also verifies that genes actually appear in the paper text.
        """
        if not self.associations:
            logging.warning("No associations to validate")
            return

        # Step 1: Validate all associations against HGNC database
        self.validation_results = self.gene_validator.validate_associations(
            self.associations
        )

        # Step 2: Verify genes actually exist in the paper text
        paper_text_upper = self.paper_text.upper()
        verified_associations = []
        verified_results = []

        for assoc, result in zip(self.associations, self.validation_results):
            if isinstance(assoc, dict):
                gene = (assoc.get("gene") or "").strip().upper()
            else:
                gene = (assoc[0] or "").strip().upper()

            # Check if gene appears in paper text (case-insensitive)
            # Look for gene as whole word to avoid false positives (e.g., "CD4" in "CD40")
            gene_in_paper = False
            if gene:
                # Pattern: word boundary + gene + word boundary (or followed by non-letter)
                import re

                gene_pattern = r"\b" + re.escape(gene) + r"(?![A-Za-z])"
                if re.search(gene_pattern, paper_text_upper):
                    gene_in_paper = True

            # Only keep if: (1) passes HGNC validation AND (2) exists in paper text
            min_confidence = getattr(config, "GENE_VALIDATION_MIN_CONFIDENCE", 0.5)
            if result.confidence_score >= min_confidence and gene_in_paper:
                verified_associations.append(assoc)
                verified_results.append(result)
            elif not gene_in_paper:
                logging.debug(
                    f"Filtered out {gene}: not found in paper text (HGNC valid: {result.is_valid_gene})"
                )

        # Filter associations based on confidence threshold
        self.validated_associations = verified_associations

        # Log validation results
        total_associations = len(self.associations)
        validated_count = len(self.validated_associations)
        validation_rate = (
            validated_count / total_associations if total_associations > 0 else 0
        )

        # Count how many were filtered for each reason
        hgnc_valid_but_not_in_paper = 0
        for assoc, result in zip(self.associations, self.validation_results):
            if result.confidence_score >= min_confidence:
                if isinstance(assoc, dict):
                    gene = (assoc.get("gene") or "").strip().upper()
                else:
                    gene = (assoc[0] or "").strip().upper()
                if gene:
                    gene_pattern = r"\b" + re.escape(gene) + r"(?![A-Za-z])"
                    if not re.search(gene_pattern, paper_text_upper):
                        hgnc_valid_but_not_in_paper += 1

        logging.info(
            f"Gene validation: {validated_count}/{total_associations} associations passed validation ({validation_rate:.1%})"
        )
        if hgnc_valid_but_not_in_paper > 0:
            logging.info(
                f"  - {hgnc_valid_but_not_in_paper} genes filtered out: HGNC valid but not found in paper text"
            )

        # Log detailed results for low-confidence associations
        low_confidence = [
            result
            for result in self.validation_results
            if result.confidence_score < min_confidence
        ]
        if low_confidence:
            logging.info(
                f"Low confidence associations filtered out: {len(low_confidence)}"
            )
            for result in low_confidence[:3]:  # Show first 3 as examples
                logging.info(
                    f"  - {result.gene} ({result.variant}): {result.confidence_score:.2f} confidence, source: {result.validation_source}"
                )

        # Update associations for downstream processing
        # De-duplicate generic terms and repeated pairs
        seen = set()
        deduped = []
        generic_terms = {"HIF-1", "VEGF", "NOTCH", "ADIPONECTIN"}
        for assoc in self.validated_associations:
            if isinstance(assoc, dict):
                g = (assoc.get("gene") or "").strip().upper()
                v = (assoc.get("variant") or "").strip().upper()
                # Normalize placeholder variants to empty to avoid duplicate gene-only prompts
                if v in {"N/A", "NA", "NONE"}:
                    v = ""
                if g in generic_terms:
                    continue
                key = (g, v)
            else:
                g, v = assoc
                g = (g or "").strip().upper()
                v = (v or "").strip().upper()
                if v in {"N/A", "NA", "NONE"}:
                    v = ""
                if g in generic_terms:
                    continue
                key = (g, v)
            if key in seen:
                continue
            seen.add(key)
            # Preserve original gene casing but normalized variant value
            if isinstance(assoc, dict):
                deduped.append({"gene": assoc.get("gene", ""), "variant": v})
            else:
                deduped.append((assoc[0], v))

        self.associations = deduped

    def _add_validation_metadata(self, df: pd.DataFrame):
        """
        Add validation metadata to the results DataFrame.

        Args:
            df: DataFrame with extracted gene information
        """
        if not self.validation_results:
            return

        # Create validation metadata columns
        df["validation_confidence"] = 0.0
        df["validation_source"] = "unknown"
        df["validation_suggestions"] = ""

        # Map results back to DataFrame rows (normalize case and variant placeholders)
        def _norm_gene(g: str) -> str:
            return (g or "").strip().upper()

        def _norm_variant(v: str) -> str:
            v = (v or "").strip().upper()  # Make case-insensitive for matching
            if v in {"N/A", "NA", "NONE"}:
                return ""
            return v

        # Create a lookup map for faster matching
        validation_map = {}
        for result in self.validation_results:
            norm_gene = _norm_gene(result.gene)
            norm_variant = _norm_variant(result.variant)
            key = (norm_gene, norm_variant)
            # Store result, preferring higher confidence if duplicate keys exist
            if (
                key not in validation_map
                or result.confidence_score > validation_map[key].confidence_score
            ):
                validation_map[key] = result

        logging.info(f"Validation map created with {len(validation_map)} entries:")
        for key, result in list(validation_map.items())[:5]:  # Show first 5
            logging.info(
                f"  {key}: confidence={result.confidence_score}, source={result.validation_source}"
            )

        for i, row in df.iterrows():
            gene_name = _norm_gene(row.get("gene_name", ""))
            variant_name = _norm_variant(row.get("variant_name", ""))
            key = (gene_name, variant_name)
            logging.info(
                f"Row {i}: Looking for gene='{gene_name}', variant='{variant_name}' -> key={key}"
            )

            # Try exact match first
            if key in validation_map:
                result = validation_map[key]
                df.at[i, "validation_confidence"] = result.confidence_score
                df.at[i, "validation_source"] = result.validation_source
                df.at[i, "validation_suggestions"] = (
                    "; ".join(result.suggestions) if result.suggestions else ""
                )
                continue

            # Try gene-only match (for gene-level associations)
            if variant_name == "" and (gene_name, "") in validation_map:
                result = validation_map[(gene_name, "")]
                df.at[i, "validation_confidence"] = result.confidence_score
                df.at[i, "validation_source"] = result.validation_source
                df.at[i, "validation_suggestions"] = (
                    "; ".join(result.suggestions) if result.suggestions else ""
                )
                continue

            # If still no match, log for debugging
            logging.debug(
                f"No validation result found for gene={gene_name}, variant={variant_name}"
            )

        logging.info(f"Added validation metadata to {len(df)} result rows")

    def _add_citation_validation_metadata(self, df: pd.DataFrame):
        """
        Add citation validation metadata to the results DataFrame.

        Args:
            df: DataFrame with extracted gene information
        """
        try:
            if not config.ENABLE_CITATION_VALIDATION:
                logging.info("Citation validation disabled in configuration")
                return

            if not hasattr(self, "paper_text") or not self.paper_text:
                logging.warning("No paper text available for citation validation")
                return

            # Initialize citation validation columns (only for user-defined columns, not metadata)
            citation_columns = {}
            excluded_cols = [
                "gene_name",
                "variant_name",
                "validation_confidence",
                "validation_source",
                "validation_suggestions",
                "context_flash_fits",
                "context_pro_fits",
                "context_original_tokens",
                "context_modifications",
            ]

            for col in df.columns:
                # Skip metadata columns and columns that are already citation validation columns
                if (
                    col not in excluded_cols
                    and not col.endswith("_citation_valid")
                    and not col.endswith("_citation_confidence")
                    and not col.endswith("_citation_details")
                ):
                    citation_columns[f"{col}_citation_valid"] = False
                    citation_columns[f"{col}_citation_confidence"] = 0.0
                    citation_columns[f"{col}_citation_details"] = (
                        "No validation performed"
                    )

            # Add columns to DataFrame
            for col_name, default_value in citation_columns.items():
                df[col_name] = default_value

            # Validate citations for each row
            total_citations_validated = 0
            total_citations_found = 0

            for i, row in df.iterrows():
                row_data = row.to_dict()

                # Validate citations for all columns except gene_name and variant_name
                try:
                    from modules.gene_validator import validate_citations

                    citation_results = validate_citations(row_data, self.paper_text)

                    for result in citation_results:
                        if result.field_name in row_data:
                            # Mark as valid only if confidence meets threshold
                            is_valid = (
                                result.citation_exists
                                and result.confidence_score
                                >= config.CITATION_MIN_CONFIDENCE
                            )
                            df.at[i, f"{result.field_name}_citation_valid"] = is_valid
                            df.at[i, f"{result.field_name}_citation_confidence"] = (
                                result.confidence_score
                            )
                            df.at[i, f"{result.field_name}_citation_details"] = (
                                result.validation_details
                            )

                            total_citations_validated += 1
                            if result.citation_exists:
                                total_citations_found += 1
                except Exception as e:
                    logging.warning(f"Citation validation failed for row {i}: {e}")
                    continue
        except Exception as e:
            logging.error(f"Citation validation metadata addition failed: {e}")
            # Don't fail the entire pipeline, just skip citation validation

        # Log citation validation summary
        if total_citations_validated > 0:
            citation_accuracy = total_citations_found / total_citations_validated * 100
            logging.info(
                f"Citation validation: {total_citations_found}/{total_citations_validated} citations verified ({citation_accuracy:.1f}%)"
            )
        else:
            logging.info("No citations to validate")

        logging.info(f"Added citation validation metadata to {len(df)} result rows")

    def _validate_and_prepare_paper_text(self) -> Dict[str, Any]:
        """
        Validate paper text against model context windows and prepare for processing.

        Returns:
            Dictionary with validation results and any modifications made
        """
        from . import config

        if not config.ENABLE_CONTEXT_CHECKING:
            return {
                "failed": False,
                "flash_fits": True,
                "pro_fits": True,
                "original_tokens": 0,
                "modifications": "Context checking disabled",
                "truncation_applied": False,
            }

        # Validate against both models using static method
        try:
            from .gene_validator import ContextWindowValidator

            context_results = ContextWindowValidator.validate_paper_context(
                self.original_paper_text
            )
        except Exception as e:
            logging.warning(
                f"Context validation unavailable ({e}); skipping context checks"
            )
            return {
                "failed": False,
                "flash_fits": True,
                "pro_fits": True,
                "original_tokens": 0,
                "modifications": "Context check unavailable",
                "truncation_applied": False,
            }
        self.context_validation_results = context_results

        flash_fits = context_results["flash_model"]["fits"]
        pro_fits = context_results["pro_model"]["fits"]

        logging.info(
            f"Context validation - Flash: {context_results['flash_model']['recommendation']}"
        )
        logging.info(
            f"Context validation - Pro: {context_results['pro_model']['recommendation']}"
        )

        # If both models can handle the full text, proceed
        if flash_fits and pro_fits:
            return {
                "failed": False,
                "flash_fits": True,
                "pro_fits": True,
                "original_tokens": context_results["flash_model"]["estimated_tokens"],
                "modifications": "No modifications needed",
                "truncation_applied": False,
            }

        # If paper exceeds context limit, skip it (don't truncate)
        original_tokens = context_results["flash_model"]["estimated_tokens"]
        logging.warning(
            f"Paper text exceeds model context limit ({original_tokens:,} tokens) - skipping paper"
        )
        return {
            "failed": True,
            "flash_fits": flash_fits,
            "pro_fits": pro_fits,
            "original_tokens": original_tokens,
            "modifications": f"Skipped: exceeds context limit ({original_tokens:,} tokens)",
            "truncation_applied": False,
        }

    def _add_context_metadata(
        self, df: pd.DataFrame, context_validation: Dict[str, any]
    ):
        """
        Add context window validation metadata to the results DataFrame.

        Args:
            df: DataFrame with extracted gene information
            context_validation: Results from context validation
        """
        # Add context validation columns
        df["context_flash_fits"] = context_validation["flash_fits"]
        df["context_pro_fits"] = context_validation["pro_fits"]
        df["context_original_tokens"] = context_validation["original_tokens"]
        df["context_modifications"] = context_validation["modifications"]

        # Log context validation summary
        logging.info(f"Context validation: {context_validation['modifications']}")
