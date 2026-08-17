"""Common failure type for untrusted paper-ingestion input."""


class KnowledgeIngestionError(ValueError):
    """Base error raised when a paper source cannot be safely ingested."""
