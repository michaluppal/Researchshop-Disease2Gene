"""Prompt constants used by Stage 5 Gemini calls."""

_GENE_DISCOVERY_INSTRUCTION_ABSTRACT = (
    "You are a biomedical gene extraction assistant. "
    "Extract ALL genes, cytokines, chemokines, interleukins, and gene products mentioned in this abstract. "
    "Focus on HUMAN genes. Do not extract genes from model organisms (mouse, rat, "
    "zebrafish) unless the paper explicitly maps them to human orthologs. "
    "Use official HGNC gene symbols (e.g. IL6 not interleukin-6, IFNG not interferon-gamma, CXCL9 not chemokine ligand 9, CSF1 not M-CSF). "
    "Include the specific variant (HGVS notation, rsID, etc.) if one is mentioned alongside the gene. "
    "If no specific variant is mentioned for a gene, use an empty string for variant. "
    "Only extract genes that are ACTUALLY mentioned in the text. Do NOT hallucinate or invent genes. "
    "CRITICAL DISAMBIGUATION: Only extract genes that the paper studies at the molecular or genetic level "
    "(e.g., gene expression, polymorphisms/variants, mutations, protein interactions, signaling pathways, gene regulation). "
    "Do NOT extract abbreviations that are used solely as clinical laboratory measurements or diagnostic test results "
    "(e.g., 'ESR 78 mm/h' is a lab value, not the ESR1 gene; 'AST 120 U/L' is a liver function test, not the GOT1 gene; "
    "'CRP 45 mg/L' is an inflammatory marker measurement, not the CRP gene). "
    "If a paper discusses both the clinical measurement AND the gene/protein at a molecular level, "
    "only extract it as a gene if the paper explicitly discusses it at the molecular level "
    "(e.g., gene expression, genetic variants, mRNA/protein levels, polymorphisms, pathway involvement)."
)

_GENE_DISCOVERY_INSTRUCTION_FULLTEXT = (
    "You are a biomedical gene extraction assistant. "
    "Extract ALL genes, cytokines, chemokines, interleukins, growth factors, receptors, and gene products mentioned in this paper. "
    "Use official HGNC gene symbols (e.g. IL6 not interleukin-6, IFNG not interferon-gamma, CXCL9 not chemokine ligand 9, CSF1 not M-CSF, IL17A not IL-17A). "
    "Include the specific variant (HGVS notation, rsID, etc.) if one is mentioned alongside the gene. "
    "If no specific variant is mentioned for a gene, use an empty string for variant. "
    "Only extract genes that are ACTUALLY discussed in the paper text. Do NOT hallucinate or invent genes that are not in the text. "
    "CRITICAL DISAMBIGUATION: Only extract genes that the paper studies at the molecular or genetic level "
    "(e.g., gene expression, polymorphisms/variants, mutations, protein interactions, signaling pathways, gene regulation). "
    "Do NOT extract abbreviations that are used solely as clinical laboratory measurements or diagnostic test results "
    "(e.g., 'ESR 78 mm/h' is a lab value, not the ESR1 gene; 'AST 120 U/L' is a liver function test, not the GOT1 gene; "
    "'CRP 45 mg/L' is an inflammatory marker measurement, not the CRP gene). "
    "If a paper discusses both the clinical measurement AND the gene/protein at a molecular level, "
    "only extract it as a gene if the paper explicitly discusses it at the molecular level "
    "(e.g., gene expression, genetic variants, mRNA/protein levels, polymorphisms, pathway involvement)."
)

_FIGURE_ANALYSIS_INSTRUCTION = (
    "You are analyzing a biomedical research figure. "
    "Extract gene symbols and specific variants that are explicitly visible in the figure text, "
    "axes labels, legends, annotations, or caption context. "
    "Use official HGNC gene symbols when possible. "
    "If no variant is shown, return an empty string for variant. "
    "Do not guess genes that are not explicitly shown."
)

_DETAIL_EXTRACTION_CRITICAL_INSTRUCTIONS = (
    "\n\nCRITICAL INSTRUCTIONS:"
    "\n- For gene_name and variant_name: Use exactly the values provided in Associations JSON."
    '\n- If variant_name is empty in Associations JSON, keep variant_name as empty string "".'
    "\n- Each gene is INDEPENDENT. You MUST fill in values for EVERY gene in the list, even if multiple genes appear together in the paper. Do NOT leave gene-level rows empty because another gene was already filled."
    "\n- Always include one gene-only row per gene (variant_name empty). Put gene-level facts specific to THAT gene in those rows."
    "\n- In variant rows (variant_name non-empty) for the same gene: provide only variant-specific details; if none, leave those variant rows empty."
    "\n- Do NOT repeat the same sentence across multiple VARIANT rows of the SAME gene. But across different genes, each gene gets its own independent facts even if the paper discusses them together."
    "\n- For any field that is filled, provide a separate '{Field} Citation' as a direct quote or page/section reference. Leave citation empty if the field is empty."
    "\n- Do NOT output placeholders like 'No supporting citation found in paper'. Use empty string instead."
    "\n- Format for gene_name and variant_name: Just the name (e.g., 'BRCA1' or 'rs123456')."
    "\n- Do NOT combine answers and citations in the same field."
    "\n- VERBATIM NUMBERS AND UNITS: Copy all numerical values and their units EXACTLY as written in the paper. Do NOT convert, round, or substitute units. For example: if the paper says '242 mg/L', write '242 mg/L' — never '242 mg/dl' or '0.242 g/L'. If the paper says 'p < 0.01', write 'p < 0.01' — not 'p=0.01'."
    "\n- NO ELLIPSIS IN CITATIONS: Citation fields must be verbatim excerpts from the paper — do NOT use '...', '[...]', or any other ellipsis or truncation. If the full sentence is too long, quote only the most specific relevant clause. If you cannot provide a verbatim quote, leave the citation field empty."
    "\n- CITATION SOURCE PRIORITY: Prefer citing prose sentences from Results/Discussion/Methods. If the ONLY textual support for a finding is in a table with no accompanying prose sentence, you MAY cite the table in this exact format: '[Table N] caption_text: relevant_cell_values' (e.g., '[Table 2] Gene expression in tumor samples: BRCA1 | p=0.001 | FC=2.5'). Never cite raw number sequences without table label and column context."
    "\n- GENE-NAMED CITATIONS: Every citation field must include at least one sentence that explicitly names the gene, its protein product, or one of its known aliases/abbreviations (e.g. 'BNP', 'NT-proBNP' for NPPB; 'PSA' for KLK3). If the most relevant sentence does not name the gene (e.g. it says 'heart injury markers' or 'the biomarker'), you may add AT MOST ONE immediately adjacent sentence — the sentence that directly precedes or directly follows it in the same paragraph with no section heading, subsection title, or paragraph break between them. Do NOT reach into Methods, definitions blocks, supplementary tables, or any other section to find the gene name. If no immediately adjacent sentence in the same paragraph names the gene, leave the citation field empty."
)
