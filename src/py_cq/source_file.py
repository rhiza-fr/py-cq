"""Process-scoped cache of parsed source files, shared across one ``cq check``.

Within a single run the same ``.py`` file is otherwise read and parsed several
times: by the normalized context hash, the coverage parser, the interrogate
parser, and the LLM formatters. :class:`SourceFile` parses each file at most
once and exposes lazy projections (functions, classes, docstring presence) that
downstream consumers walk instead of re-parsing.

The cache is keyed on ``(path, size, mtime)`` so a content change (which bumps
``mtime``) misses and forces a fresh parse; correctness never depends on a hit.
"""

import ast
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FuncInfo:
    """A function or class definition discovered in a source file.

    ``signature`` is the rendered ``def`` line for functions and ``""`` for
    classes (no consumer needs a class signature). ``kind`` is ``"function"``
    or ``"class"``.
    """

    name: str
    kind: str
    lineno: int
    end_lineno: int
    has_docstring: bool
    signature: str


def _docstring_invariant_digest(tree: ast.AST) -> str:
    """Return an md5 of ``tree`` with docstrings removed, leaving ``tree`` intact.

    Docstring statements are temporarily detached, the tree is dumped and
    hashed, then they are reattached - so the digest is docstring-invariant
    without parsing a second time or mutating the tree that other consumers
    share. Safe because the hash pass runs single-threaded before the tool pool.
    """
    detached = []
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                detached.append((node, body[0]))
                node.body = body[1:]
    digest = hashlib.md5(ast.dump(tree).encode()).hexdigest()  # nosec
    for node, doc in detached:
        node.body = [doc, *node.body]
    return digest


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Return the signature of the function definition as a string."""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args = ast.unparse(node.args)
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({args}){returns}"


class SourceFile:
    """Lazily-realized view of one source file: text, AST, and projections.

    Fields are computed on first access and cached. ``.tree`` stays pristine
    (docstrings intact) so multiple consumers can share it; ``.norm_digest``
    derives its docstring-stripped digest from a throwaway reparse rather than
    mutating ``.tree``.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._raw: bytes | None = None
        self._text: str | None = None
        self._tree: ast.AST | None = None
        self._parsed = False
        self._norm_digest: str | None = None
        self._definitions: list[FuncInfo] | None = None

    def _read_bytes(self) -> bytes:
        if self._raw is None:
            self._raw = Path(self.path).read_bytes()
        return self._raw

    @property
    def text(self) -> str:
        """Return the file contents decoded as UTF-8 (undecodable bytes replaced)."""
        if self._text is None:
            self._text = self._read_bytes().decode("utf-8", "replace")
        return self._text

    @property
    def tree(self) -> ast.AST | None:
        """Return the parsed AST, or ``None`` if the file can't be parsed."""
        if not self._parsed:
            self._parsed = True
            try:
                self._tree = ast.parse(self.text)
            except (SyntaxError, ValueError):
                self._tree = None
        return self._tree

    @property
    def norm_digest(self) -> str:
        """Return a docstring/comment/format-invariant digest of the file.

        Falls back to a byte digest when the file can't be parsed (e.g. a
        mid-edit syntax error), so callers always get a usable digest.
        """
        if self._norm_digest is None:
            tree = self.tree
            if tree is None:
                self._norm_digest = hashlib.md5(self._read_bytes()).hexdigest()  # nosec
            else:
                self._norm_digest = _docstring_invariant_digest(tree)
        return self._norm_digest

    @property
    def definitions(self) -> list[FuncInfo]:
        """Return every function and class definition, in source order."""
        if self._definitions is None:
            defs: list[FuncInfo] = []
            tree = self.tree
            if tree is not None:
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        defs.append(
                            FuncInfo(
                                node.name,
                                "function",
                                node.lineno,
                                getattr(node, "end_lineno", node.lineno),
                                ast.get_docstring(node) is not None,
                                _signature(node),
                            )
                        )
                    elif isinstance(node, ast.ClassDef):
                        defs.append(
                            FuncInfo(
                                node.name,
                                "class",
                                node.lineno,
                                getattr(node, "end_lineno", node.lineno),
                                ast.get_docstring(node) is not None,
                                "",
                            )
                        )
                defs.sort(key=lambda d: d.lineno)
            self._definitions = defs
        return self._definitions

    @property
    def functions(self) -> list[FuncInfo]:
        """Return the function definitions only (no classes), in source order."""
        return [d for d in self.definitions if d.kind == "function"]

    @property
    def module_has_docstring(self) -> bool:
        """Return True if the module has a docstring."""
        tree = self.tree
        return isinstance(tree, ast.Module) and ast.get_docstring(tree) is not None


# Process-scoped memo: (path, size, mtime) -> SourceFile. A stale mtime only
# forces a re-parse that reproduces the same projections, so correctness never
# depends on this cache (matches the lock-free design: a duplicate parse is
# harmless and GIL-serialized).
_source_cache: dict[tuple[str, int, float], SourceFile] = {}


def get_source(path: str) -> SourceFile:
    """Return the cached :class:`SourceFile` for ``path``, creating it on miss.

    Keyed on ``(canonical_path, size, mtime)``; a content change misses and
    re-parses. The path is canonicalized (absolute + OS case folding) so the
    hash pass and the parsers - which spell the same file differently (relative
    vs. resolved/posix) - share one cache entry.

    Raises:
        OSError: If ``path`` cannot be stat'd.
    """
    s = os.stat(path)
    key = (os.path.normcase(os.path.abspath(path)), s.st_size, s.st_mtime)
    sf = _source_cache.get(key)
    if sf is None:
        sf = SourceFile(path)
        _source_cache[key] = sf
    return sf
