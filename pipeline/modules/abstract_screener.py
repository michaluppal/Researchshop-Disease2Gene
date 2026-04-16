# modules/abstract_screener.py

"""
FIX #2: Abstract-Based Pre-Screening

Lightweight keyword and pattern-based filtering to identify papers with genetic content
BEFORE expensive AI analysis. This is a FREE (no API cost) filter that catches papers
unlikely to contain gene-variant data.

Expected Impact: 30% additional waste reduction after publication type filtering.
Cost: Zero API calls, minimal CPU time (regex + keyword matching)
"""

import logging
import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Set, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(module)s] - %(message)s')

# Terms that appear almost exclusively in molecular biology contexts,
# distinguishing molecular genetics papers from clinical-measurement papers.
# Used by the molecular-context precision gate to prevent clinical outcome
# papers (that mention gene-like biomarker names) from passing screening.
MOLECULAR_CONTEXT_TERMS = [
    'mutation', 'variant', 'polymorphism', 'allele', 'genotype', 'haplotype',
    'gene expression', 'overexpression', 'overexpressed', 'downregulation',
    'upregulation', 'knockdown', 'knockout', 'transgenic',
    'sequencing', 'exome', 'gwas', 'snp', 'whole genome',
    'methylation', 'epigenetic', 'histone',
    'somatic', 'germline',
    'mrna', 'sirna', 'mirna', 'lncrna', 'ncrna',
    'translocation', 'chromosomal', 'karyotype', 'copy number',
    'exon', 'intron', 'promoter', 'enhancer',
    'crispr', 'gene editing',
    'proteomics', 'transcriptome',
    'locus', 'loci',
    'deletion', 'amplification',
]


@dataclass
class ScreeningDecision:
    """Forensic audit record for a single paper's abstract screening outcome."""
    pmid: str
    passed: bool
    score: int
    threshold: int
    positive_keywords: List[str]
    negative_keywords: List[str]
    gene_symbols_found: List[str]
    reason: str  # '' if passed, else 'below_threshold' or 'abstract_too_short'
    is_mandatory: bool


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
        ('fusion', 2), ('translocation', 2), ('inversion', 1),
        # Expanded: epigenetics, functional genomics, immune/cytokine
        ('crispr', 3), ('gene editing', 3), ('epigenetic', 2),
        ('histone', 2), ('promoter', 1), ('enhancer', 1),
        ('lncrna', 2), ('mirna', 2), ('sirna', 2), ('ncrna', 2),
        ('gwas', 3), ('whole genome', 2), ('exome', 3),
        ('proteomics', 2), ('phosphorylation', 1), ('ubiquitination', 1),
        ('cytokine', 2), ('interleukin', 2), ('chemokine', 2),
        ('interferon', 2), ('receptor', 1), ('signaling pathway', 2),
        ('kinase', 1), ('pathway', 1), ('biomarker', 2),
        ('dysregulation', 2), ('overexpressed', 2), ('knockdown', 2),
        ('knockout', 2), ('transgenic', 2), ('phenotype', 1),
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

    # Look for gene symbol patterns
    # Pattern 1: uppercase letters + digits (BRCA1, TP53, IL6, CXCL9)
    # Pattern 2: well-known gene symbols without digits (TNF, EGFR, PTEN, MYC, etc.)
    gene_pattern_with_digits = r'\b[A-Z]{2,6}[0-9]{1,3}\b'
    gene_pattern_alpha_only = r'\b(?:TNF|EGFR|PTEN|MYC|KRAS|NRAS|BRAF|STAT|MAPK|MTOR|VEGF|VEGFA|NOTCH|ERBB|FGFR|PDGF|PDGFRA|PDGFRB|AKT|PIK3CA|RB1|CDKN|CDK|MDM|SMAD|TGFB|NFKB|BCL|BAX|FAS|CASP|JAK|CTLA|IKZF|ARID|KMT|IDH|FLT|KIT|RET|MET|ALK|ROS|ABL|SRC|RAF|MEK|ERK|JNK|WNT|APC|AXIN|PARP|ATM|ATR|CHEK|RAD|XRCC|MLH|MSH|PMS|HLA|IFNG|IFNA|CSF|CXCL|CCL|CCR|CXCR|TLR|NLRP|HMGB|SOD|GPX|CAT|HIF|EPAS|VHL|NRF|KEAP|GATA|RUNX|ETV|FOXP|RORC|TBET|EOMES|IRF|BATF|BCL6|PRDM|CTCF|DNMT|TET|HDAC|SIRT|EZH|SUZ|BMI|RING|PRC|SWI|SNF|BRD|ARID|MLL|DOT|NSD|SETD|KDM|LSD|JMJD|PHF|TRIM|RNF|UBE|USP|CUL|SKP|FBXW|BTRC|VCP|HSP|HSPA|HSPB|GRP|BIP)\b'

    raw_text = title + ' ' + abstract
    gene_mentions_digits = re.findall(gene_pattern_with_digits, raw_text)
    gene_mentions_alpha = re.findall(gene_pattern_alpha_only, raw_text)
    gene_mentions = gene_mentions_digits + gene_mentions_alpha

    # Filter out common false positives
    false_positives = {
        'HIV1', 'HIV2', 'COVID19', 'H1N1', 'H5N1', 'SARS', 'MERS',
        'TABLE1', 'TABLE2', 'TABLE3', 'FIGURE1', 'FIGURE2', 'FIGURE3',
        'GROUP1', 'GROUP2', 'STUDY1', 'STUDY2', 'PHASE1', 'PHASE2', 'PHASE3',
        'TYPE1', 'TYPE2', 'GRADE1', 'GRADE2', 'GRADE3', 'STAGE1', 'STAGE2',
    }
    filtered_genes = [g for g in gene_mentions if g not in false_positives]
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

    # Molecular-context precision gate
    # Clinical papers can score above threshold from ambiguous signals alone
    # (e.g., cytokine, interleukin, biomarker keywords + gene-like symbol
    # patterns like IL6). If gene symbols were found but the abstract lacks
    # any unambiguously molecular term, reduce the gene symbol contribution —
    # these symbols are likely clinical biomarker names, not molecular targets.
    has_molecular_context = any(term in combined for term in MOLECULAR_CONTEXT_TERMS)
    molecular_context_penalty = 0
    if gene_count > 0 and not has_molecular_context:
        molecular_context_penalty = gene_count + 3  # Halve gene contribution + flat penalty
        score -= molecular_context_penalty

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
        'disease_gene_phrases': phrase_matches,
        'has_molecular_context': has_molecular_context,
        'molecular_context_penalty': molecular_context_penalty,
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


def screen_papers_with_decisions(
    paper_details: Dict[str, Dict],
    threshold: int = 5,
    mandatory_pmids: Optional[Set[str]] = None,
) -> Tuple[Dict[str, Dict], List[ScreeningDecision]]:
    """
    Batch screen papers and return forensic decisions alongside the filtered results.

    Calls has_genetic_content() internally for each paper and builds a ScreeningDecision
    record capturing the full scoring breakdown. Mandatory PMIDs always pass regardless
    of score.

    Args:
        paper_details: Dict mapping PMID -> paper info (must include 'title' and 'abstract')
        threshold: Minimum score to pass screening
        mandatory_pmids: Set of PMIDs that must pass regardless of score

    Returns:
        Tuple of (screened_papers dict, list of ScreeningDecision records)
    """
    if mandatory_pmids is None:
        mandatory_pmids = set()

    screened_papers = {}
    decisions: List[ScreeningDecision] = []
    total = len(paper_details)
    passed_count = 0

    for pmid, info in paper_details.items():
        title = info.get('title', '')
        abstract = info.get('abstract', '')
        is_mandatory = pmid in mandatory_pmids

        should_process, confidence, details = has_genetic_content(abstract, title, threshold)

        # Mandatory PMIDs always pass
        if is_mandatory and not should_process:
            should_process = True

        # Build reason string
        if should_process:
            reason = ''
        elif details.get('reason') == 'abstract_too_short':
            reason = 'abstract_too_short'
        else:
            reason = 'below_threshold'

        decision = ScreeningDecision(
            pmid=pmid,
            passed=should_process,
            score=details.get('raw_score', 0),
            threshold=threshold,
            positive_keywords=details.get('positive_keywords', []),
            negative_keywords=details.get('negative_keywords', []),
            gene_symbols_found=details.get('gene_symbols_found', []),
            reason=reason,
            is_mandatory=is_mandatory,
        )
        decisions.append(decision)

        # Enrich paper info with screening results (same as screen_papers)
        enriched_info = info.copy()
        enriched_info['screening_passed'] = should_process
        enriched_info['screening_confidence'] = confidence
        enriched_info['screening_details'] = details
        screened_papers[pmid] = enriched_info

        if should_process:
            passed_count += 1

    logging.info(
        f"Abstract screening complete: {passed_count}/{total} passed "
        f"({passed_count/total*100:.1f}% pass rate, "
        f"{len(mandatory_pmids)} mandatory)" if total > 0 else
        "Abstract screening complete: 0 papers"
    )

    return screened_papers, decisions


def decisions_to_dicts(decisions: List[ScreeningDecision]) -> List[Dict]:
    """Serialize a list of ScreeningDecision records to plain dicts for JSON output."""
    return [asdict(d) for d in decisions]

