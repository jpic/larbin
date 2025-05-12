import networkx as nx
import os
import asyncio
from typing import List, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import cli2
from larbin import db

grep_ast_patterns = {
    'python': 'import_statement,import_from_statement',
    'java': 'import_declaration',
    'cpp': 'include_directive'
}

language_id_map = {'python': 1, 'java': 2, 'cpp': 3}
symbol_type_map = {'python': 'import', 'java': 'import', 'cpp': 'include'}

class ImportAnalyzer:
    def __init__(self, project, file_paths: List[str], language_name: str):
        self.project = project
        self.file_paths = file_paths
        self.language_name = language_name
        self.grep_pattern = grep_ast_patterns.get(language_name)
        if not self.grep_pattern:
            raise ValueError(f"No grep-ast pattern for {language_name}")
        self.graph = nx.DiGraph()
        self.file_id_map: Dict[str, int] = {}
        self.file_metadata: Dict[str, float] = {}
        self.queue = cli2.Queue()
        self.grep_cmd = ['grep-ast', self.grep_pattern]

    async def _preload_metadata(self):
        loop = asyncio.get_event_loop()
        for path in self.file_paths:
            try:
                self.file_metadata[path] = await loop.run_in_executor(None, os.path.getmtime, path)
            except OSError:
                self.file_metadata[path] = 0.0

    async def _ensure_file(self, session: AsyncSession, path: str) -> int:
        if path in self.file_id_map:
            return self.file_id_map[path]
        result = await session.execute(select(db.File).where(db.File.path == path))
        file = result.scalar_one_or_none()
        if not file:
            file = db.File(
                path=path,
                mtime=self.file_metadata.get(path, 0.0),
                language_id=language_id_map.get(self.language_name, 1),
                token_count=0
            )
            session.add(file)
            await session.flush()
            self.file_id_map[path] = file.id
        else:
            self.file_id_map[path] = file.id
        return self.file_id_map[path]

    async def _get_symbol(self, session: AsyncSession, file_id: int, name: str, line: int) -> int:
        result = await session.execute(
            select(db.Symbol).where(
                db.Symbol.file_id == file_id,
                db.Symbol.name == name,
                db.Symbol.line_start == line
            )
        )
        symbol = result.scalar_one_or_none()
        if not symbol:
            symbol = db.Symbol(
                file_id=file_id,
                type=symbol_type_map.get(self.language_name, 'dependency'),
                name=name,
                line_start=line,
                score=0
            )
            session.add(symbol)
            await session.flush()
            return symbol.id
        return symbol.id

    async def _add_import(self, session: AsyncSession, symbol_id: int, file_id: int):
        result = await session.execute(
            select(db.Import).where(
                db.Import.symbol_id == symbol_id,
                db.Import.file_id == file_id
            )
        )
        if not result.scalar_one_or_none():
            session.add(db.Import(symbol_id=symbol_id, file_id=file_id))

    async def _analyze_file(self, path: str) -> bool:
        session_factory = await self.project.db.session_factory()
        async with session_factory() as session:
            try:
                # Check mtime against DB
                result = await session.execute(select(db.File).where(db.File.path == str(path)))
                db_file = result.scalar_one_or_none()
                current_mtime = self.file_metadata.get(path, 0.0)
                if db_file and db_file.mtime >= current_mtime:
                    return True  # Skip unchanged file

                file_id = await self._ensure_file(session, path)
                cmd = self.grep_cmd + [path]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=1024 * 1024
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    cli2.log.error(f"grep-ast failed for {path}: {stderr.decode()}")
                    return False

                imports = []
                for line in stdout.decode().splitlines():
                    parts = line.split(':', 2)
                    if len(parts) >= 3:
                        try:
                            line_num = int(parts[1])
                            name = parts[2].strip()
                            if name:
                                imports.append((name, line_num))
                        except ValueError:
                            continue

                file_node = f"file:{path}"
                self.graph.add_node(file_node)
                new_imports = []
                for name, line in imports:
                    if self.language_name == 'python':
                        name = name.split('.')[0]
                    elif self.language_name == 'java':
                        name = name.split('.')[-1]
                    elif self.language_name == 'cpp':
                        name = os.path.basename(name)
                    self.graph.add_node(name)
                    self.graph.add_edge(file_node, name)
                    symbol_id = await self._get_symbol(session, file_id, name, line)
                    new_imports.append({'symbol_id': symbol_id, 'file_id': file_id})

                for imp in new_imports:
                    await self._add_import(session, imp['symbol_id'], imp['file_id'])
                await session.commit()
                return True
            except Exception as e:
                cli2.log.exception(f"Error processing {path}: {str(e)}")
                await session.rollback()
                return False

    async def _rank_symbols(self):
        session_factory = await self.project.db.session_factory()
        async with session_factory() as session:
            try:
                scores = nx.pagerank(self.graph, alpha=0.85, max_iter=100, tol=1e-6)
                updates = []
                for name, score in scores.items():
                    if not name.startswith("file:"):
                        result = await session.execute(
                            select(db.Symbol).where(db.Symbol.name == name)
                        )
                        symbol = result.scalar_one_or_none()
                        if symbol:
                            symbol.score = score
                            updates.append(symbol)
                session.add_all(updates)
                await session.commit()
            except Exception as e:
                cli2.log.error(f"Error ranking symbols: {str(e)}")
                await session.rollback()

    async def analyze_and_store_imports(self):
        await self._preload_metadata()
        tasks = [self._analyze_file(path) for path in self.file_paths]
        await self.queue.run(*tasks)
        await self._rank_symbols()
        if self.queue.results:
            successful = sum(1 for r in self.queue.results if r)
            cli2.log.info(f"Processed {successful}/{len(self.file_paths)} files")
