"""Optional tree-sitter markdown fast path (plugin stub)."""


def available() -> bool:
    try:
        import tree_sitter_markdown  # noqa: F401

        return True
    except Exception:
        return False
