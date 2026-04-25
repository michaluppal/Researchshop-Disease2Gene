#!/bin/bash
# Stop hook: detects learning signals and nudges /reflect + AUDIT.md update

CONTEXT=$(cat)

# Pipeline/medical-specific: changes to accuracy, safeguards, or correctness
PIPELINE_PATTERNS="false.positive|false.negative|precision|recall|hallucin|grounding|confidence.threshold|validation.gate|gene.symbol|variant.pattern|extraction.fail|missed.gene|wrong.gene|incorrect.gene|pubtator|gemini.prompt|screening.threshold"

# General learning signals: fixes, discoveries, corrections
STRONG_PATTERNS="fixed|workaround|gotcha|that'?s wrong|check again|we already|should have|discovered|realized|turns out|regression|wasn'?t working|now works|root cause|the bug was|the issue was"

if echo "$CONTEXT" | grep -qiE "$PIPELINE_PATTERNS"; then
  echo '{"decision": "approve", "systemMessage": "Pipeline or accuracy behaviour changed this session. Run /reflect and update AUDIT.md — document the change, the reasoning, and any tradeoff accepted."}'
elif echo "$CONTEXT" | grep -qiE "$STRONG_PATTERNS"; then
  echo '{"decision": "approve", "systemMessage": "This session involved fixes or discoveries. Run /reflect to capture learnings in .claude/rules/ and AUDIT.md."}'
else
  echo '{"decision": "approve"}'
fi
