# modules/abstract_screener.py

"""
Abstract-Based Pre-Screening Module

Lightweight keyword and pattern-based filtering to identify papers with genetic content
before AI analysis. Uses regex and keyword matching to filter out papers unlikely to 
contain gene-variant data, reducing unnecessary API calls.
"""

import re
import logging
from typing import Tuple, Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(module)s] - %(message)s')


def has_genetic_content(abstract: str, title: str, threshold: int = 5) -> Tuple[bool, float, Dict[str, Any]]:
    """
    Fast heuristic check if paper likely contains gene-variant data.
    
    Args:
        abstract: Paper abstract text
        title: Paper title
        threshold: Minimum score required to pass (default: 5)
    
    Returns:
        (should_process, confidence_score, details)
        - should_process: bool, whether to proceed with AI analysis
        - confidence_score: float 0-1, normalized confidence
        - details: dict with scoring breakdown for debugging
    """
    if not abstract or len(abstract) < 100:
        return False, 0.0, {'reason': 'abstract_too_short', 'length': len(abstract) if abstract else 0}
    
    combined = f"{title} {abstract}".lower()
    
    # Positive signals (weighted by relevance)
    genetic_keywords = [
        ('mutation', 3), ('variant', 3), ('polymorphism', 3),
        ('gene expression', 2), ('genotype', 2), ('allele', 2),
        ('snp', 3), ('deletion', 2), ('amplification', 2),
        ('methylation', 2), ('rna', 1), ('protein expression', 1),
        ('molecular', 1), ('genetic', 1), ('genomic', 2),
        ('sequencing', 2), ('exon', 2), ('intron', 1),
        ('transcription', 1), ('translation', 1), ('mrna', 2),
        ('somatic', 2), ('germline', 2), ('inheritance', 1),
        ('chromosomal', 2), ('karyotype', 2), ('copy number', 2),
        ('fusion', 2), ('translocation', 2), ('inversion', 1)
    ]
    
    # Negative signals (red flags for non-genetic papers)
    negative_keywords = [
        'systematic review', 'meta-analysis', 'literature review',
        'overview', 'commentary', 'perspective', 'editorial',
        'rehabilitation', 'psychological', 'quality of life',
        'screening program', 'public health', 'policy',
        'economic burden', 'cost-effectiveness', 'health care costs',
        'nursing', 'palliative care', 'end of life',
        'patient education', 'communication', 'decision making',
        'disparities', 'access to care', 'health insurance'
    ]
    
    score = 0
    positive_matches = []
    negative_matches = []
    
    # Score positive signals
    for keyword, weight in genetic_keywords:
        if keyword in combined:
            score += weight
            positive_matches.append(keyword)
    
    # Penalize negative signals
    for keyword in negative_keywords:
        if keyword in combined:
            score -= 5  # Heavy penalty
            negative_matches.append(keyword)
    
    # Look for gene symbol patterns (BRCA1, TP53, EGFR, etc.)
    # Pattern: 2-6 uppercase letters followed by 1-3 digits
    gene_pattern = r'\b[A-Z]{2,6}[0-9]{1,3}\b'
    gene_mentions = re.findall(gene_pattern, title + ' ' + abstract)
    
    # Filter out common false positives (e.g., HIV1, COVID19)
    filtered_genes = [g for g in gene_mentions if g not in ['HIV1', 'HIV2', 'COVID19', 'H1N1', 'H5N1']]
    gene_count = len(set(filtered_genes))  # Unique gene symbols
    score += gene_count * 2
    
    # Look for variant nomenclature patterns
    # Examples: c.123A>G, p.Val600Glu, rs123456, L858R, T790M
    variant_patterns = [
        r'[cp]\.[A-Z][a-z]{2}\d+[A-Z][a-z]{2}',  # p.Val600Glu
        r'[cp]\.\d+[ACGT]>[ACGT]',  # c.123A>G
        r'\brs\d{5,}',  # rs123456 (dbSNP)
        r'\b[A-Z]\d{3,4}[A-Z]\b',  # L858R, T790M
        r'del[A-Z]?\d+',  # deletion
        r'ins[A-Z]?\d+',  # insertion
    ]
    
    variant_matches = []
    for pattern in variant_patterns:
        matches = re.findall(pattern, abstract)
        variant_matches.extend(matches)
    
    variant_count = len(set(variant_matches))
    score += variant_count * 3  # Variants are strong signals
    
    # Bonus for specific gene-disease language
    disease_gene_phrases = [
        'associated with', 'linked to', 'mutations in',
        'variants in', 'polymorphisms in', 'alterations in',
        'overexpression of', 'downregulation of', 'loss of'
    ]
    
    phrase_matches = []
    for phrase in disease_gene_phrases:
        if phrase in combined:
            score += 1
            phrase_matches.append(phrase)
    
    # Normalize score to 0-1 confidence (max reasonable score ~30-40)
    max_score = 40.0
    confidence = min(score / max_score, 1.0) if score > 0 else 0.0
    
    should_process = score >= threshold
    
    details = {
        'raw_score': score,
        'threshold': threshold,
        'positive_keywords': positive_matches,
        'negative_keywords': negative_matches,
        'gene_symbols_found': filtered_genes[:10],  # Sample
        'gene_symbol_count': gene_count,
        'variant_patterns_found': variant_matches[:5],  # Sample
        'variant_count': variant_count,
        'disease_gene_phrases': phrase_matches
    }
    
    if not should_process:
        logging.info(f"Abstract screening REJECTED paper (score: {score}/{threshold})")
    else:
        logging.info(f"Abstract screening PASSED paper (score: {score}/{threshold}, confidence: {confidence:.2f})")
    
    return should_process, confidence, details


def screen_papers(paper_details: Dict[str, Dict[str, Any]], threshold: int = 5) -> Dict[str, Dict[str, Any]]:
    """
    Batch screen multiple papers by their abstracts.
    
    Args:
        paper_details: Dict mapping PMID -> paper info (must include 'title' and 'abstract')
        threshold: Minimum score to pass screening
    
    Returns:
        Dict mapping PMID -> enriched paper info (with screening results)
    """
    screened_papers = {}
    total = len(paper_details)
    passed = 0
    rejected = 0
    
    for pmid, info in paper_details.items():
        title = info.get('title', '')
        abstract = info.get('abstract', '')
        
        should_process, confidence, details = has_genetic_content(abstract, title, threshold)
        
        # Enrich paper info with screening results
        enriched_info = info.copy()
        enriched_info['screening_passed'] = should_process
        enriched_info['screening_confidence'] = confidence
        enriched_info['screening_details'] = details
        
        screened_papers[pmid] = enriched_info
        
        if should_process:
            passed += 1
        else:
            rejected += 1
    
    logging.info(f"Abstract screening complete: {passed}/{total} passed ({passed/total*100:.1f}%), {rejected} rejected")
    
    return screened_papers


def get_passed_pmids(screened_papers: Dict[str, Dict[str, Any]]) -> list:
    """
    Extract list of PMIDs that passed screening, sorted by confidence (descending).
    
    Args:
        screened_papers: Output from screen_papers()
    
    Returns:
        List of PMIDs sorted by screening confidence
    """
    passed = [(pmid, info['screening_confidence']) 
              for pmid, info in screened_papers.items() 
              if info.get('screening_passed', False)]
    
    # Sort by confidence descending
    passed.sort(key=lambda x: x[1], reverse=True)
    
    return [pmid for pmid, _ in passed]

