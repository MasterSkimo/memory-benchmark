"""Basic Memory adapter backed by its Markdown sync and FTS5 search services."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

_IMPORTED = False
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "de", "des", "du", "en",
    "est", "for", "from", "how", "in", "is", "it", "la", "le", "les", "of", "on",
    "or", "que", "quelle", "quel", "quels", "quelles", "the", "to", "un", "une", "what",
    "when", "where", "which", "who", "with", "dans", "pour", "sur", "aux", "ou", "et",
}


def _load_backend():
    global _IMPORTED
    # Basic Memory 0.13.1 ConfigManager has no supported config-directory
    # selector: it resolves config directly from HOME/Path.home(). Keep HOME
    # untouched. Candidate-local persistence is provided by run.py's filesystem
    # mount at the genuine HOME/.basic-memory location.
    if not _IMPORTED:
        import basic_memory.config as config_module
        _IMPORTED = True
    else:
        import basic_memory.config as config_module
    return config_module


class BasicMemoryAdapter:
    def __init__(self, corpus: Path, organization_id: str, knowledge_space_id: str):
        self.corpus = Path(corpus).resolve()
        self.organization_id = organization_id
        self.knowledge_space_id = knowledge_space_id
        self._validate_path_components()
        scope_digest = hashlib.sha256(json.dumps(
            [organization_id, knowledge_space_id], ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")).hexdigest()[:32]
        self.project_name = f"bench-{scope_digest}"
        self.source_scope_path = self.corpus / organization_id / knowledge_space_id
        if not self.source_scope_path.is_dir():
            raise ValueError("authorized corpus scope does not exist")
        if self.source_scope_path.is_symlink():
            raise ValueError("authorized corpus scope must not be a symlink")
        self.scope_path = Path(__file__).resolve().parent / "runtime-home" / "projects" / scope_digest
        self._validate_scope_documents()
        if self.scope_path.exists():
            shutil.rmtree(self.scope_path)
        self.scope_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.source_scope_path, self.scope_path)
        self._scope_private_permalinks(scope_digest)
        self.project = None
        self.search_service = None
        self.entity_repository = None
        self.file_service = None
        self.sync_report = None
        self._setup()

    def _validate_path_components(self):
        for part in (self.organization_id, self.knowledge_space_id):
            if not isinstance(part, str) or not part or part in {".", ".."} or "/" in part or "\\" in part:
                raise ValueError("organization and knowledge-space IDs must be safe path components")
            if Path(part).name != part:
                raise ValueError("organization and knowledge-space IDs must be safe path components")

    def _validate_scope_documents(self):
        import frontmatter

        if self.source_scope_path.resolve(strict=True) != self.source_scope_path.absolute():
            raise ValueError("authorized scope contains a symlink or non-canonical path")
        for directory, subdirs, files in os.walk(self.source_scope_path, followlinks=False):
            base = Path(directory)
            for child in subdirs:
                if (base / child).is_symlink():
                    raise ValueError("symlink directories are not allowed in the authorized corpus")
            for name in files:
                path = base / name
                if path.suffix.lower() != ".md":
                    continue
                if path.is_symlink():
                    raise ValueError("symlink documents are not allowed in the authorized corpus")
                metadata = frontmatter.load(path).metadata
                canonical_id = path.relative_to(self.corpus).with_suffix("").as_posix()
                if metadata.get("organization_id") != self.organization_id:
                    raise ValueError(f"document organization_id does not match authorized scope: {path.name}")
                if metadata.get("knowledge_space_id") != self.knowledge_space_id:
                    raise ValueError(f"document knowledge_space_id does not match authorized scope: {path.name}")
                if metadata.get("document_id") != canonical_id:
                    raise ValueError(f"document_id is missing or non-canonical: {path.name}")
                revision = metadata.get("revision")
                if not isinstance(revision, (str, int)) or not str(revision).strip():
                    raise ValueError(f"revision is required: {path.name}")

    def _scope_private_permalinks(self, scope_digest: str):
        import frontmatter

        for path in self.scope_path.rglob("*.md"):
            relative = path.relative_to(self.scope_path).with_suffix("").as_posix()
            post = frontmatter.load(path)
            # Basic Memory 0.13.1 deletes FTS rows globally by permalink while
            # indexing. A project-unique permalink prefix prevents equal relative
            # file names in separate projects from evicting each other's rows.
            post.metadata["permalink"] = f"bench/{scope_digest}/{relative}"
            path.write_text(frontmatter.dumps(post), encoding="utf-8")

    def _setup(self):
        _load_backend()
        async def setup():
            from basic_memory import db
            from basic_memory.config import app_config, config_manager
            from basic_memory.models import Project
            from basic_memory.repository import (
                EntityRepository, ObservationRepository, RelationRepository, ProjectRepository,
            )
            from basic_memory.repository.search_repository import SearchRepository
            from basic_memory.services import EntityService, FileService
            from basic_memory.services.link_resolver import LinkResolver
            from basic_memory.services.search_service import SearchService
            from basic_memory.sync import SyncService
            from basic_memory.markdown import EntityParser, MarkdownProcessor
            from basic_memory.utils import generate_permalink

            # The candidate-local DB is initialized once; run_migrations() repeats
            # a FTS table initialization on every adapter construction. Migrations
            # run on the first setup and the migration marker makes later calls a
            # no-op, but the library's redundant FTS initialization can stall.
            if not app_config.database_path.exists() or app_config.database_path.stat().st_size == 0:
                await db.run_migrations(app_config)
            _, sessions = await db.get_or_create_db(app_config.database_path, db.DatabaseType.FILESYSTEM)
            projects = ProjectRepository(sessions)
            self.project = await projects.get_by_name(self.project_name)
            if not self.project:
                if self.project_name not in config_manager.projects:
                    config_manager.add_project(self.project_name, str(self.scope_path))
                self.project = await projects.create({
                    "name": self.project_name,
                    "path": str(self.scope_path),
                    "permalink": generate_permalink(self.project_name),
                    "is_active": True,
                })
            p = self.project
            parser = EntityParser(self.scope_path)
            files = FileService(self.scope_path, MarkdownProcessor(parser))
            entities = EntityRepository(sessions, project_id=p.id)
            observations = ObservationRepository(sessions, project_id=p.id)
            relations = RelationRepository(sessions, project_id=p.id)
            search_repo = SearchRepository(sessions, project_id=p.id)
            await search_repo.init_search_index()
            search = SearchService(search_repo, entities, files)
            resolver = LinkResolver(entities, search)
            entity_service = EntityService(parser, entities, observations, relations, files, resolver)
            sync = SyncService(app_config, entity_service, parser, entities, relations, search, files)
            self.sync_report = await sync.sync(self.scope_path, project_name=self.project_name)
            self.search_service = search
            self.entity_repository = entities
            self.file_service = files

        asyncio.run(setup())

    def search(self, question: dict, top_k: int = 5) -> dict:
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        for key, expected in (("organization_id", self.organization_id), ("knowledge_space_id", self.knowledge_space_id)):
            supplied = question.get(key, expected)
            if supplied != expected:
                raise PermissionError(f"question {key} differs from adapter authorization")
        query = question.get("question") or question.get("text") or question.get("query") or ""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("question must contain non-empty question/text/query")
        # Basic Memory's FTS5 parser treats a whole natural-language question as
        # one quoted prefix phrase. Convert it to an OR over quoted terms so
        # French/English question framing and punctuation do not force a phrase
        # that the note never contains. Search/ranking remains Basic Memory FTS5.
        terms = list(dict.fromkeys(
            token.lower() for token in re.findall(r"[\wÀ-ÿ]+", query, flags=re.UNICODE)
            if len(token) > 1 and token.lower() not in _STOP_WORDS
        ))
        fts_query = " OR ".join(f'"{term}"' for term in terms) or query.strip()

        async def run_search():
            from basic_memory.schemas.search import SearchQuery, SearchItemType
            return await self.search_service.search(
                SearchQuery(text=fts_query, entity_types=[SearchItemType.ENTITY]), limit=top_k
            )

        rows = asyncio.run(run_search())
        hits = []
        file_reads = 0
        bytes_read = 0
        for row in rows:
            rel = Path(row.file_path)
            # Basic Memory emits paths relative to the authorized project root.
            absolute = (self.scope_path / rel).resolve()
            if self.scope_path not in absolute.parents or not absolute.is_file():
                continue
            source_path = self.source_scope_path / rel
            if source_path.is_symlink() or not source_path.is_file():
                raise RuntimeError("Basic Memory returned a source path outside the validated Markdown set")
            source = source_path.read_text(encoding="utf-8")
            file_reads += 1
            bytes_read += len(source.encode("utf-8"))
            import frontmatter
            metadata = frontmatter.loads(source).metadata
            doc_id = metadata.get("document_id")
            revision = metadata.get("revision")
            canonical_id = source_path.relative_to(self.corpus).with_suffix("").as_posix()
            if doc_id != canonical_id:
                raise RuntimeError("Basic Memory returned non-canonical document provenance")
            if metadata.get("organization_id") != self.organization_id or metadata.get("knowledge_space_id") != self.knowledge_space_id:
                raise RuntimeError("Basic Memory returned a document outside the authorized scope")
            if not isinstance(revision, (str, int)) or not str(revision).strip():
                raise RuntimeError("Basic Memory returned a document without a revision")
            text = row.content_snippet or row.title or ""
            hits.append({"document_id": doc_id, "revision": revision, "score": row.score, "text": text})
        return {"hits": hits, "backend_calls": 1, "file_reads": file_reads, "bytes_read": bytes_read}


def create_adapter(corpus, organization_id, knowledge_space_id):
    return BasicMemoryAdapter(Path(corpus), organization_id, knowledge_space_id)
