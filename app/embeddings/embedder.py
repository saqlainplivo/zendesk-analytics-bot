"""OpenAI embeddings generation."""

import logging
from typing import List, Optional

import openai
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)

# Configure OpenAI
openai.api_key = settings.openai_api_key


class Embedder:
    """Generate embeddings using OpenAI API."""

    def __init__(
        self,
        model: str = None,
        dimension: int = None,
    ):
        """
        Initialize embedder.

        Args:
            model: OpenAI embedding model (defaults to settings)
            dimension: Embedding dimension (defaults to settings)
        """
        self.model = model or settings.embedding_model
        self.dimension = dimension or settings.embedding_dimension
        self.client = openai.OpenAI(api_key=settings.openai_api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text to embed

        Returns:
            Embedding vector as list of floats

        Raises:
            openai.OpenAIError: If API call fails after retries
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        try:
            # Truncate text if too long (max ~8191 tokens for text-embedding-3-small)
            text = text[:32000]  # Conservative limit

            response = self.client.embeddings.create(
                model=self.model,
                input=text,
                encoding_format="float"
            )

            embedding = response.data[0].embedding

            # Validate dimension
            if len(embedding) != self.dimension:
                logger.warning(
                    f"Expected dimension {self.dimension}, got {len(embedding)}"
                )

            return embedding

        except openai.OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error generating embedding: {e}")
            raise

    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 100
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches.

        Args:
            texts: List of input texts
            batch_size: Number of texts to embed per API call

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = self._embed_batch_internal(batch)
            embeddings.extend(batch_embeddings)

            logger.info(f"Embedded batch {i//batch_size + 1}: {len(batch)} texts")

        return embeddings

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _embed_batch_internal(self, texts: List[str]) -> List[List[float]]:
        """
        Internal method to embed a batch of texts.

        Args:
            texts: List of texts (max 100)

        Returns:
            List of embeddings
        """
        try:
            # Truncate long texts
            truncated_texts = [text[:32000] if text else "" for text in texts]

            response = self.client.embeddings.create(
                model=self.model,
                input=truncated_texts,
                encoding_format="float"
            )

            embeddings = [data.embedding for data in response.data]
            return embeddings

        except openai.OpenAIError as e:
            logger.error(f"OpenAI API error in batch: {e}")
            raise

    def embed_ticket(
        self,
        subject: str,
        description: Optional[str] = None,
        comments: Optional[List[str]] = None
    ) -> List[float]:
        """
        Generate embedding for a ticket by combining its fields.

        Args:
            subject: Ticket subject
            description: Ticket description
            comments: List of comment texts

        Returns:
            Embedding vector
        """
        # Combine ticket fields into a single text
        parts = [f"Subject: {subject}"]

        if description:
            parts.append(f"Description: {description}")

        if comments:
            # Include first few comments
            comment_texts = comments[:5]  # Limit to avoid too long text
            if comment_texts:
                parts.append("Comments: " + " | ".join(comment_texts))

        combined_text = "\n".join(parts)
        return self.embed_text(combined_text)

    def get_ticket_content_for_embedding(
        self,
        subject: str,
        description: Optional[str] = None,
        comments: Optional[List[str]] = None
    ) -> str:
        """
        Get the combined text content used for embedding.

        Useful for storing alongside the embedding vector.

        Args:
            subject: Ticket subject
            description: Ticket description
            comments: List of comment texts

        Returns:
            Combined text
        """
        parts = [f"Subject: {subject}"]

        if description:
            parts.append(f"Description: {description}")

        if comments:
            comment_texts = comments[:5]
            if comment_texts:
                parts.append("Comments: " + " | ".join(comment_texts))

        return "\n".join(parts)
