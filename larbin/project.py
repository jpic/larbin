from pathlib import Path
from sqlalchemy.sql import or_, and_
from typing import List, Optional
import cli2
import functools
import os
import subprocess
import textwrap
from .context import Context
from . import db


class ProjectDB:
    def __init__(self, project):
        self.project = project
        cli2.cfg.defaults.update(dict(
            LARBIN_DB=f'sqlite+aiosqlite:///{project.path}/.larbin/db.sqlite3',
        ))
        self._engine = None
        self._session = None
        self._session_factory = None

    def engine(self):
        if not self._engine:
            self._engine = db.create_async_engine(cli2.cfg["LARBIN_DB"], echo=False)
        return self._engine

    async def session_factory(self):
        if not self._session_factory:
            async with self.engine().begin() as conn:
                await conn.run_sync(lambda connection: db.Base.metadata.create_all(connection, checkfirst=True))

            self._session_factory = db.async_sessionmaker(
                self.engine(),
                class_=db.AsyncSession,
                expire_on_commit=False,
            )
        return self._session_factory

    async def session(self):
        if not self._session:
            self._session = await self.session_make()
        return self._session

    async def session_make(self):
        return (await self.session_factory())()

    async def session_open(self):
        if not self._session:
            self._session = await self.session_factory()
        return self._session

    async def session_close(self):
        if self._session is not None:
            await self.engine().dispose()


class ProjectMetaclass(type):
    @property
    def current(self):
        current = getattr(self, '_current', None)
        if not current:
            self._current = Project(os.getcwd())
        return self._current


class Project(metaclass=ProjectMetaclass):
    current = None

    def __init__(self, path=None):
        self.path = Path(path or os.getcwd())
        self.db = ProjectDB(self)
        self._contexts = dict()

    @functools.cached_property
    def files(self):
        return cli2.Find(self.path, flags='-type f').run()

    @property
    def contexts(self):
        """Return a dict of contexts, create a default context if necessary."""
        for path in self.contexts_path.iterdir():
            if path.name not in self._contexts:
                self._contexts[path.name] = Context(self, path)

        for name in ('default', 'project'):
            if name in self._contexts:
                continue
            self._contexts[name] = Context(self, self.contexts_path / name)
            self._contexts[name].path.mkdir(exist_ok=True, parents=True)

        return self._contexts

    @functools.cached_property
    def contexts_path(self):
        """Return the path to the project context directories."""
        path = self.path / '.larbin/contexts'
        path.mkdir(exist_ok=True, parents=True)
        return path


project = Project(os.getcwd())
