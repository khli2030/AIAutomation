"""Service layer package — business logic lives here (not in API routers)."""

# Intentionally do not import AnsibleExecutionService here so Phase 2 import
# paths do not load the execution module unless explicitly requested.
__all__: list[str] = []
