import asyncio
import aiofiles
from tree_sitter_language_pack import get_parser, SupportedLanguage
import os
import cli2
from larbin import db
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from typing import Literal


language_map = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".cpp": "cpp",
    ".c": "c",
}


class CodeIndexer:
    def __init__(self, project):
        self.project = project
        self.parsers: dict[str, object] = {}  # Tree-sitter parsers
        self.global_language_cache: dict[
            str, db.Language
        ] = {}  # Pre-populated global cache
        self.setup_parsers()

    def setup_parsers(self):
        """Initialize tree-sitter parsers for supported languages."""
        supported_languages: list[Literal[SupportedLanguage]] = [
            "python",
            "javascript",
            "typescript",
            "cpp",
            "c",
        ]

        for lang_name in supported_languages:
            try:
                parser = get_parser(lang_name)
                self.parsers[lang_name] = parser
            except Exception as e:
                cli2.log.exception(f"Failed to load {lang_name} parser: {e}")

    async def initialize_language_cache(self):
        """Pre-populate the global language cache with all supported languages."""
        supported_languages = [
            "python",
            "javascript",
            "typescript",
            "cpp",
            "c",
        ]

        async with await self.project.db.session_make() as session:
            for lang_name in supported_languages:
                language = (
                    await session.execute(
                        select(db.Language).filter_by(name=lang_name)
                    )
                ).scalar_one_or_none()

                if not language:
                    language = db.Language(name=lang_name)
                    session.add(language)
                    try:
                        await session.commit()
                    except IntegrityError:
                        await session.rollback()
                        # Retry fetch after rollback in case another process inserted it
                        language = (
                            await session.execute(
                                select(db.Language).filter_by(name=lang_name)
                            )
                        ).scalar_one_or_none()

                self.global_language_cache[lang_name] = language
            cli2.log.info(
                "Global language cache initialized",
                languages=self.global_language_cache.keys(),
            )

    async def get_or_create_language(
        self, lang_name: str, session: db.AsyncSession, local_cache: dict
    ) -> db.Language:
        """Get or create a language entry, using a local per-task cache and handling IntegrityError."""
        # Check local cache first
        if lang_name in local_cache:
            return local_cache[lang_name]

        # Check global cache next
        if lang_name in self.global_language_cache:
            local_cache[lang_name] = self.global_language_cache[lang_name]
            return local_cache[lang_name]

        # Fallback to database if not in either cache
        language = (
            await session.execute(
                select(db.Language).filter_by(name=lang_name)
            )
        ).scalar_one_or_none()

        if not language:
            language = db.Language(name=lang_name)
            session.add(language)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                # Fetch the language that was inserted by another task
                language = (
                    await session.execute(
                        select(db.Language).filter_by(name=lang_name)
                    )
                ).scalar_one_or_none()
                if not language:
                    raise  # Something else went wrong

        local_cache[lang_name] = language
        return language

    async def process_file(
        self, filepath: str, session: db.AsyncSession, local_cache: dict
    ):
        """Process a single file and extract symbols asynchronously, using a local cache."""
        cli2.log.debug("processing", filepath=filepath)
        ext = os.path.splitext(filepath)[1].lower()

        lang_name = language_map.get(ext)
        if not lang_name or lang_name not in self.parsers:
            return

        mtime = os.path.getmtime(filepath)
        existing_file = (
            await session.execute(
                select(db.File).filter_by(path=str(filepath))
            )
        ).scalar_one_or_none()

        if existing_file and existing_file.mtime >= mtime:
            return

        # Async file reading
        async with aiofiles.open(filepath, "rb") as f:
            content = await f.read()

        # Parse in a thread pool since tree-sitter is CPU-bound
        loop = asyncio.get_running_loop()
        parser = self.parsers[lang_name]
        tree = await loop.run_in_executor(None, parser.parse, content)

        language = await self.get_or_create_language(
            lang_name, session, local_cache
        )

        if existing_file:
            existing_file.mtime = mtime
            existing_file.language_id = language.id
            file = existing_file
        else:
            file = db.File(
                path=str(filepath),
                mtime=mtime,
                language_id=language.id,
                token_count=len(content.split()),
            )
            session.add(file)
            await session.flush()  # Ensure file.id is available

        symbols = self.extract_symbols(tree, content, lang_name)
        await self.update_symbols(file.id, symbols, session)

        await session.commit()
        cli2.log.info("processed", filepath=filepath)

    def extract_symbols(self, tree, content: bytes, lang_name: str):
        """Extract symbols from the syntax tree (remains synchronous as it's called in a thread)."""
        symbols = []
        tree.walk()

        def traverse(node):
            node_type = node.type
            # Avoid decoding here unless necessary, since we only need it for names
            if node_type == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8", errors="ignore").strip()  # Trim here
                    if name.startswith("__"):
                        score = 1
                    elif name.startswith("_"):
                        score = 3
                    else:
                        score = 10
                    symbols.append(
                        {
                            "type": "function",
                            "name": name,
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                            "score": score,
                        }
                    )
            elif node_type == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8", errors="ignore").strip()  # Trim here
                    symbols.append(
                        {
                            "type": "class",
                            "name": name,
                            "line_start": node.start_point[0] + 1,
                            "line_end": node.end_point[0] + 1,
                            "score": 15,
                        }
                    )

            for child in node.children:
                traverse(child)

        traverse(tree.root_node)
        return symbols

    async def update_symbols(
        self, file_id: int, symbols: list[dict], session: db.AsyncSession
    ):
        """Update symbols by deleting existing ones and inserting new ones asynchronously."""
        await session.execute(
            delete(db.Symbol).where(db.Symbol.file_id == file_id)
        )

        if symbols:
            new_symbols = [
                db.Symbol(
                    file_id=file_id,
                    type=s["type"],
                    name=s["name"].strip(),  # Double-check trim here for safety
                    line_start=s["line_start"],
                    line_end=s["line_end"],
                    score=s.get("score", 0),
                )
                for s in symbols
            ]
            session.add_all(new_symbols)

    async def index_repo_async(self):
        """Index all files in the repository asynchronously."""
        # Pre-populate the global language cache
        await self.initialize_language_cache()

        async def file_callback(filepath):
            # Each task gets its own local cache
            local_cache = {}
            try:
                async with await self.project.db.session_make() as session:
                    await self.process_file(
                        filepath,
                        session,
                        local_cache,
                    )
                cli2.log.debug(f"Processed: {filepath}")
            except Exception:
                cli2.log.exception("processing error", path=filepath)

        # Collect file paths synchronously
        finder = cli2.Find(
            root=self.project.path,
            flags='-type f',
            glob_include=[f'*{ext}' for ext in language_map],
            glob_exclude=['.git'],
        )
        file_paths = [f for f in finder.run()]

        # Process files concurrently with cli2.Queue
        queue = cli2.Queue()  # Uses default 12 workers

        async def process_file(filepath):
            await file_callback(filepath)
            return filepath  # Optional: return something to track in queue.results

        # Create tasks for each file
        tasks = [process_file(fp) for fp in file_paths]

        # Run all tasks through the queue
        await queue.run(*tasks)

        # Optional: Check results if needed
        if queue.results:
            processed_files = len(queue.results)
            print(f"Processed {processed_files}/{len(file_paths)} files")
        return queue.results
