import cli2
import larbin
import flow2
import functools
import prompt2
import textwrap
import os
from pathlib import Path


class InspectPlugin(larbin.Plugin):
    @functools.cached_property
    def path(self):
        return self.context.project.path / 'LARBIN.md'

    def model(self, name):
        return prompt2.Model([f'{name}.extensions', 'inspect', 'architect'])

    @cli2.cmd
    async def inspect(self):
        """
        larbin inspect plugin has inspected your project to build a list of
        coding rules that will be used by other larbin plugins to guide the AI.

        It is written in LARBIN.md which you can freely edit at any time.
        """
        project_files = cli2.Find(
            flags='-type f',
        ).run()

        # keep one file per extension
        extensions = {str(f).split('.')[-1]: f for f in project_files}.values()

        flow = flow2.Flow('larbin.inspect')
        context = await flow.run(
            project_files=project_files,
            extension_paths=extensions,
        )
        output = context['inspect_output']
        with open('LARBIN.md', 'w') as f:
            f.write(output)

        print(cli2.highlight(output, 'Markdown'))

        print(cli2.t.g.b('WRITTEN TO') + ' LARBIN.md')

    async def template(self):
        if not self.path.exists():
            if cli2.confirm('LARBIN.md does not exist, generate?'):
                await self.inspect()
                if cli2.confirm('Edit LARBIN.md before proceeding?'):
                    cli2.editor(path=self.path)

        if self.path.exists():
            with self.path.open('r') as f:
                print(cli2.t.g('INJECTED LARBIN.md'))
                return f.readlines()
