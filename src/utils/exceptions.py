"""Application-wide custom exception hierarchy."""

class EcommercePlatformError(Exception):
    """Base exception for all domain-specific platform errors."""
    pass


class ConfigurationError(EcommercePlatformError):
    """Raised when application configuration is invalid or missing."""
    pass


class DataValidationError(EcommercePlatformError):
    """Raised when incoming dataset records fail schema or business rule validation."""
    pass


class IngestionError(EcommercePlatformError):
    """Raised when ingestion process encounters an unrecoverable failure."""
    pass


class DatabaseError(EcommercePlatformError):
    """Raised for database connectivity, session, or transaction failures."""
    pass


class AnalyticsError(EcommercePlatformError):
    """Raised during analytics query generation or computation."""
    pass


class ModelTrainingError(EcommercePlatformError):
    """Raised when machine learning model training or validation fails."""
    pass


class PredictionError(EcommercePlatformError):
    """Raised during inference or risk segmentation scoring."""
    pass


class GeminiAssistantError(EcommercePlatformError):
    """Raised when GenAI client or tool execution encounters an error."""
    pass


class SecurityViolationError(EcommercePlatformError):
    """Raised when an unauthorized operation, SQL injection risk, or payload violation is detected."""
    pass
