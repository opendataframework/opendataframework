"""Name-casing helpers shared by ``Namespace`` and its subclasses."""

import re


def kebab(name: str) -> str:
    """Convert CamelCase to kebab-case. MetricsFetcher → metrics-fetcher."""
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def snake(name: str) -> str:
    """Convert CamelCase to snake_case. MetricsFetcher → metrics_fetcher."""
    return kebab(name).replace("-", "_")


def normalize(name: str) -> str:
    """Normalize any name form to kebab-case.

    Accepts PascalCase, snake_case, or kebab-case and returns kebab-case:
    MetricsFetcher → metrics-fetcher
    metrics_fetcher → metrics-fetcher
    metrics-fetcher → metrics-fetcher
    """
    if any(c.isupper() for c in name):
        return kebab(name)
    return name.replace("_", "-")
