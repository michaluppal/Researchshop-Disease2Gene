#!/usr/bin/env python3
"""Standalone PubTator3 gene lookup for gold standard annotation.

Usage: python3 python/scripts/pubtator_lookup.py <PMID> [<PMID2> ...]
Output: JSON to stdout

Queries PubTator3 API for gene annotations, resolves each to HGNC symbol
via GeneValidator, and outputs structured results with text mentions.

Requires: python/.venv with pipeline dependencies installed.
Must be run from the project root (python/ must be importable).
"""

import json
import sys
import os

# Add python/ to path so modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.pubtator_tool import extract_with_pubtator, NCBIGeneTool
from modules.gene_validator import GeneValidator


def lookup_pmid(pmid: str, validator: GeneValidator) -> dict:
    """Query PubTator3 for a PMID and resolve genes to HGNC symbols."""
    genes, variants = extract_with_pubtator(pmid)

    results = []
    seen_symbols = set()

    for gene in genes:
        # Resolve to canonical HGNC symbol
        resolved, source = validator.resolve_gene_symbol(gene.symbol)
        symbol = resolved if resolved else gene.symbol

        if symbol.upper() in seen_symbols:
            # Merge text_mentions into existing entry
            for r in results:
                if r['symbol'].upper() == symbol.upper():
                    for mention in gene.text_mentions:
                        if mention not in r['as_appears']:
                            r['as_appears'].append(mention)
                    break
            continue

        seen_symbols.add(symbol.upper())

        # Collect all text forms this gene appears as
        as_appears = list(set(gene.text_mentions)) if gene.text_mentions else [gene.symbol]
        # Add the canonical symbol if not already present
        if symbol not in as_appears and symbol.upper() not in [a.upper() for a in as_appears]:
            as_appears.insert(0, symbol)

        results.append({
            'symbol': symbol,
            'as_appears': as_appears,
            'ncbi_gene_id': gene.ncbi_gene_id,
            'resolution_source': source,
            'source': 'pubtator'
        })

    variant_results = []
    for variant in variants:
        variant_results.append({
            'text': variant.text,
            'variant_type': variant.variant_type,
            'rsid': getattr(variant, 'rsid', None),
            'gene_id': getattr(variant, 'gene_id', None),
        })

    return {
        'pmid': pmid,
        'genes': results,
        'variants': variant_results,
        'gene_count': len(results),
        'variant_count': len(variant_results)
    }


def main():
    if len(sys.argv) < 2:
        print('Usage: python3 pubtator_lookup.py <PMID> [<PMID2> ...]', file=sys.stderr)
        sys.exit(1)

    pmids = sys.argv[1:]
    validator = GeneValidator()

    if len(pmids) == 1:
        result = lookup_pmid(pmids[0], validator)
        print(json.dumps(result, indent=2))
    else:
        results = [lookup_pmid(pmid, validator) for pmid in pmids]
        print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
