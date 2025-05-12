from .project import Project
from .context import Context
from .plugin import Plugin


project = Project()
context = Context.current(project)
