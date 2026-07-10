"""Transport-neutral application failure contract."""


class ApplicationError(Exception):
    """Base for expected domain and application failures handled at the API edge."""
