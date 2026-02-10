# modules/variant_normalizer.py

"""
Normalize variant names to standard HGVS format where possible.

Handles common variant descriptions and converts them to HGVS notation.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def normalize_variant(variant: str) -> str:
    """
    Normalize variant name to HGVS format where possible.
    
    Examples:
    - "5382INSC" -> "c.5382insC" (if cDNA)
    - "6633DEL5" -> "c.6633del5" (if cDNA)
    - "RARE DELETERIOUS MISSENSE VARIANT" -> "" (too generic)
    - "MUTATION" -> "" (too generic)
    - "1100DELC; P.I157T" -> "c.1100delC" or "p.Ile157Thr" (if can parse)
    
    Args:
        variant: Variant string from extraction
        
    Returns:
        Normalized variant string, or original if cannot normalize
    """
    if not variant or not isinstance(variant, str):
        return ""
    
    variant = variant.strip()
    
    # Too generic - return empty
    generic_patterns = [
        r"^(MUTATION|MUTATIONS)$",
        r"^.*(RARE|DELETERIOUS|PATHOGENIC|TRUNCATING).*(VARIANT|MUTATION).*$",
        r"^(N/A|NA|NONE)$",
    ]
    for pattern in generic_patterns:
        if re.match(pattern, variant, re.IGNORECASE):
            return ""
    
    # Try to normalize common patterns
    
    # Pattern: "5382INSC" -> "c.5382insC"
    match = re.match(r"^(\d+)(INS|DEL|ins|del)([A-Z]+)$", variant, re.IGNORECASE)
    if match:
        pos, op, bases = match.groups()
        op_lower = op.lower()
        if op_lower == "ins":
            return f"c.{pos}ins{bases}"
        elif op_lower == "del":
            return f"c.{pos}del{bases}"
    
    # Pattern: "6633DEL5" -> "c.6633del5" (deletion with length)
    match = re.match(r"^(\d+)(DEL|del)(\d+)$", variant, re.IGNORECASE)
    if match:
        pos, op, length = match.groups()
        return f"c.{pos}del{length}"
    
    # Pattern: "P.I157T" -> "p.Ile157Thr" (try to normalize amino acid)
    match = re.match(r"^[Pp]\.([A-Z])(\d+)([A-Z])$", variant)
    if match:
        aa1, pos, aa2 = match.groups()
        # Convert single letter to three letter code (basic mapping)
        aa_map = {
            'A': 'Ala', 'R': 'Arg', 'N': 'Asn', 'D': 'Asp', 'C': 'Cys',
            'Q': 'Gln', 'E': 'Glu', 'G': 'Gly', 'H': 'His', 'I': 'Ile',
            'L': 'Leu', 'K': 'Lys', 'M': 'Met', 'F': 'Phe', 'P': 'Pro',
            'S': 'Ser', 'T': 'Thr', 'W': 'Trp', 'Y': 'Tyr', 'V': 'Val'
        }
        aa1_full = aa_map.get(aa1, aa1)
        aa2_full = aa_map.get(aa2, aa2)
        return f"p.{aa1_full}{pos}{aa2_full}"
    
    # Pattern: Multiple variants separated by semicolon
    if ";" in variant:
        parts = [p.strip() for p in variant.split(";")]
        normalized_parts = [normalize_variant(p) for p in parts if p]
        # Return first valid normalized variant, or empty if none
        for part in normalized_parts:
            if part:
                return part
        return ""
    
    # If it already looks like HGVS, return as-is
    hgvs_patterns = [
        r"^[cgp]\.\d+",
        r"^rs\d+$",
        r"^[A-Z]\d+[A-Z]$",  # Simple amino acid substitution
    ]
    for pattern in hgvs_patterns:
        if re.match(pattern, variant, re.IGNORECASE):
            return variant
    
    # If contains description text, return empty (too generic)
    if len(variant.split()) > 3:  # More than 3 words = likely description
        return ""
    
    # Return original if cannot normalize
    return variant


def normalize_variants_in_dataframe(df) -> None:
    """
    Normalize variant names in a DataFrame's "Variant Name" column.
    
    Modifies the DataFrame in-place.
    """
    if df.empty or "Variant Name" not in df.columns:
        return
    
    df["Variant Name"] = df["Variant Name"].apply(normalize_variant)
    
    logger.info(f"Normalized variant names in {len(df)} rows")

