import larbin
import prompt2
import template2
from pathlib import Path


class Template2(template2.Template2):
    def __init__(self, plugins, paths=None, **options):
        paths = paths or []
        paths += prompt2.Prompt.paths()
        super().__init__(plugins, paths, **options)


class Code2Template2Plugin(template2.Plugin):
    # make these available in the templates
    project = larbin.project
    context = larbin.context

    def macros(self):
        return dict(prompt2='prompt2.macros.txt')

    async def repomap(self):
        return await self.context.plugins['repomap'].repomap()
