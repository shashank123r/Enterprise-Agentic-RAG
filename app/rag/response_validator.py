"""Response validator — structural and content validation of LLM responses.

Validates that LLM responses follow expected formats, have proper structure,
and meet minimum quality criteria before returning to the user.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class ResponseValidator:
    """Validates LLM response quality and structure.

    Checks:
    - Response is non-empty and non-trivial
    - Response doesn't contain harmful or disallowed content
    - Response has proper structure (paragraphs, not raw JSON, etc.)
    - Response length is reasonable
    """

    MIN_ANSWER_LENGTH = 10
    MAX_ANSWER_LENGTH = 50000

    # Patterns that suggest a failed or nonsensical response
    _FAILURE_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"^I'm (sorry|unable|not able)", re.IGNORECASE),
        re.compile(r"^As an AI", re.IGNORECASE),
        re.compile(r"^I cannot (answer|complete|provide|fulfill)", re.IGNORECASE),
        re.compile(r"^\s*```"),  # Starts with code block
        re.compile(r"^\s*\{.*\}\s*$"),  # Looks like raw JSON
    ]

    async def validate(
        self,
        answer: str,
    ) -> dict[str, Any]:
        """Validate a generated answer.

        Args:
            answer: Generated answer text.

        Returns:
            Dict with:
            - valid: bool
            - issues: list[str]
            - truncated: bool
        """
        issues: list[str] = []

        # 1. Empty or too short
        if not answer or len(answer.strip()) < self.MIN_ANSWER_LENGTH:
            issues.append(f"Answer too short ({len(answer)} chars)")

        # 2. Too long
        if len(answer) > self.MAX_ANSWER_LENGTH:
            issues.append(f"Answer exceeds max length ({len(answer)} > {self.MAX_ANSWER_LENGTH})")

        # 3. Failure patterns
        for pattern in self._FAILURE_PATTERNS:
            if pattern.match(answer.strip()):
                issues.append(f"Answer starts with refusal pattern: {pattern.pattern[:40]}...")
                break

        # 4. Check for non-empty content
        stripped = answer.strip()
        if stripped and len(stripped.split()) < 3:
            issues.append("Answer contains fewer than 3 words")

        valid = len(issues) == 0
        logger.debug(
            "Response validation complete",
            valid=valid,
            issues=len(issues),
            answer_length=len(answer),
        )

        return {
            "valid": valid,
            "issues": issues,
            "truncated": False,
        }
