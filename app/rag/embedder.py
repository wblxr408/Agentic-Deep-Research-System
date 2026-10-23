"""
BGE Embedder: generates vector embeddings for queries and documents.

Loads the configured SentenceTransformer artifact; quantization is not inferred
from a repository name.
"""

from __future__ import annotations

import logging
import asyncio
import importlib.metadata
from threading import Lock
from typing import TYPE_CHECKING

import torch

from app.config import get_settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class Embedder:
    """
    Generates vector embeddings using BGE models.

    Design decisions:
    - Lazy loading to avoid startup latency
    - Automatic device detection (CUDA/CPU)
    - Batch processing for document embedding
    - Explicit artifact revision and observed encoding metadata
    """

    def __init__(self, model_name: str | None = None, device: str | None = None):
        settings = get_settings()
        self.model_name = model_name or settings.rag.embed_model
        self.revision = settings.rag.embed_revision
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model: SentenceTransformer | None = None
        self._load_lock=Lock()
        self.last_profile:dict|None=None
        self.last_batch_coverage:list[dict]=[]
        logger.info(f"Embedder: using model={self.model_name}, device={self.device}")

    @property
    def model(self):
        with self._load_lock:
            if self._model is not None:return self._model
            try:
                from sentence_transformers import SentenceTransformer
            except ModuleNotFoundError as exc:
                raise ModuleNotFoundError(
                    "sentence_transformers is required to load the embedder model"
                ) from exc
            self._model = SentenceTransformer(self.model_name, device=self.device,revision=self.revision,trust_remote_code=False)
            logger.info("Embedder: model loaded successfully")
        return self._model

    async def embed(self, text: str) -> list[float]:
        """
        Embed a single text query.

        Args:
            text: Query text

        Returns:
            Observed model-dimensional vector (list of floats)
        """
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """
        Embed multiple texts in batches.

        Args:
            texts: List of text strings
            batch_size: Batch size for processing

        Returns:
            List of embedding vectors
        """
        if not texts:
            self.last_batch_coverage=[]
            return []
        def encode():
            from app.retrieval_features import identity,VERSION
            model=self.model
            vectors=model.encode(texts,batch_size=batch_size,normalize_embeddings=True,
                show_progress_bar=False,convert_to_numpy=True).tolist()
            default_prompt_name=getattr(model,'default_prompt_name',None)
            prompt=(getattr(model,'prompts',{}) or {}).get(default_prompt_name,'')
            profile={'schema_version':VERSION,'model':self.model_name,'requested_revision':self.revision,
                'dimension':len(vectors[0]),'normalization':'l2','encoder_method':'SentenceTransformer.encode',
                'sentence_transformers_version':importlib.metadata.version('sentence-transformers'),
                'torch_version':torch.__version__,'transformers_version':importlib.metadata.version('transformers'),
                'maximum_sequence_tokens':getattr(model,'max_seq_length',None),
                'default_prompt_name':default_prompt_name,'default_prompt_digest':identity(prompt),
                'model_reference_kind':'pinned_commit' if self.revision else 'unfrozen_reference',
                'quantization':'not_inferred_from_model_name'}
            profile['encoding_profile_id']=identity(profile)
            coverage=[]
            tokenizer=getattr(model,'tokenizer',None)
            maximum=profile['maximum_sequence_tokens']
            for text in texts:
                try:
                    tokens=tokenizer(prompt+text,add_special_tokens=True,truncation=False,return_attention_mask=False,return_token_type_ids=False)['input_ids'] if tokenizer else None
                    token_count=len(tokens) if tokens is not None else None
                    coverage.append({'input_characters':len(text),'input_tokens_with_default_prompt':token_count,
                        'maximum_sequence_tokens':maximum,'truncated':token_count>maximum if token_count is not None and isinstance(maximum,int) else None,
                        'status':'tokenizer_length_observed' if token_count is not None else 'token_length_unknown',
                        'offset_semantics':'encoder_input_length_not_original_text_remapping'})
                except (TypeError,ValueError,KeyError,AttributeError):
                    coverage.append({'input_characters':len(text),'status':'token_length_unknown','truncated':None})
            self.last_profile=profile;self.last_batch_coverage=coverage
            return vectors
        return await asyncio.to_thread(encode)

    @property
    def dimension(self) -> int:
        """Get the embedding dimension."""
        return self.model.get_sentence_embedding_dimension()

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation)."""
        return len(text) // 4
