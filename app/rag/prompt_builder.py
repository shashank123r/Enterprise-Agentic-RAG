"""Prompt builder — constructs LLM prompts with retrieved context, instructions, and conversation history.

Supports customizable system instructions, citation formats,
and token-aware construction.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.rag.token_budget import TokenBudget

logger = get_logger(__name__)

# Default system prompt for the RAG pipeline
_DEFAULT_SYSTEM_PROMPT = """You are an enterprise AI assistant. Your role is to provide accurate, well-cited answers based on the retrieved documents.

## Instructions

1. Answer using ONLY the provided context. If the context lacks sufficient information, state this clearly.

2. Cite your sources using bracketed numbers like [1], [2], etc. Each citation corresponds to a Source section in the context.

3. Every factual statement must be supported by at least one citation.

4. If asked about information not in the context, say "I don't have enough information to answer that" — never speculate.

5. Format your response clearly using markdown when helpful (headings, lists, tables).

6. When reporting numbers, statistics, or specific claims, always include the source citation.

7. Never fabricate citations or attribute information to documents that don't contain it.

8. If there are multiple relevant sources, cite all of them.

## Output Format

Provide your answer followed by the sources you referenced. Each citation should appear as [N] where N is the source number."""


class PromptBuilder:
    """Builds LLM prompts from context, instructions, and conversation history.

    Usage:
        builder = PromptBuilder()
        prompt = await builder.build(
            context="...",
            question="...",
            budget=token_budget,
            history=[{"role": "user", "content": "..."}],
        )
    """

    def __init__(self, system_prompt: str | None = None) -> None:
        self._system_prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT

    async def build(
        self,
        context: str,
        question: str,
        budget: TokenBudget,
        history: list[dict[str, str]] | None = None,
        extra_instructions: str | None = None,
    ) -> list[dict[str, str]]:
        """Build a structured prompt for the LLM.

        Constructs a messages list following the OpenAI message format:
            system: System prompt with instructions
            user: Context section + question

        Args:
            context: Formatted context string from ContextManager.
            question: User's question.
            budget: TokenBudget for accounting.
            history: Optional conversation history.
            extra_instructions: Optional additional instructions for this query.

        Returns:
            List of message dicts with 'role' and 'content' keys.
        """
        messages: list[dict[str, str]] = []

        # Step 1: System message
        system_content = self._system_prompt
        if extra_instructions:
            system_content = f"{system_content}\n\n## Additional Instructions\n{extra_instructions}"
        messages.append({"role": "system", "content": system_content})

        # Step 2: Conversation history (if any)
        if history:
            # Trim history to fit within budget
            trimmed_history = self._trim_history(history, budget)
            messages.extend(trimmed_history)

        # Step 3: User message with context and question
        if context:
            user_content = (
                f"## Context\n\n"
                f"The following sources contain information that may help answer the question.\n\n"
                f"{context}\n\n"
                f"## Question\n\n{question}"
            )
        else:
            user_content = f"## Question\n\n{question}\n\nNote: No relevant context was found. Answer based on your knowledge, but clearly state that you could not find specific sources."

        messages.append({"role": "user", "content": user_content})

        # Log token estimates
        total_chars = sum(len(m["content"]) for m in messages)
        estimated_tokens = budget.count_tokens(
            " ".join(m["content"] for m in messages)
        )
        logger.debug(
            "Prompt built",
            messages=len(messages),
            estimated_tokens=estimated_tokens,
            has_context=bool(context),
            has_history=bool(history),
        )

        return messages

    @staticmethod
    def _trim_history(
        history: list[dict[str, str]],
        budget: TokenBudget,
        max_exchanges: int = 10,
    ) -> list[dict[str, str]]:
        """Trim conversation history to fit within budget.

        Keeps the most recent exchanges, limited by max_exchanges.

        Args:
            history: Full conversation history.
            budget: TokenBudget for estimation.
            max_exchanges: Maximum number of exchanges to keep.

        Returns:
            Trimmed history list.
        """
        if len(history) <= max_exchanges:
            return history

        # Keep only the last N exchanges
        return history[-max_exchanges:]
