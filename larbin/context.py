import cli2
import functools
import hashlib
import importlib
import os
import prompt2
import textwrap
import yaml
from pathlib import Path


class ContextPaths:
    def __init__(self, context):
        self.context = context

    def add(self, *paths, confirmed=False):
        data = self.context.data.copy()

        if 'paths' not in data:
            data['paths'] = []

        paths = [path for path in paths if path not in data['paths']]

        if not paths:
            return

        if len(paths) > 1 and not confirmed:
            confirmed = cli2.confirm(
                f'Add all files to context? {", ".join(paths)}'
            )

        for path in paths:
            if confirmed or cli2.confirm(f'Add {path} to context?'):
                data['paths'].append(path)

        self.context.update(paths=data['paths'])

    def extract_from_response(self, response):
        return [
            token.strip('`')
            for token in response.split()
            if os.path.exists(token)
            or os.path.exists(token.strip('`'))
        ]

    def add_from_response(self, response):
        self.add(*self.extract_from_response(response))

    def list(self):
        return self.context.data['paths']


class ContextCommands:
    def __init__(self, context):
        self.context = context

    def add(self, command):
        data = self.context.data.copy()
        if 'commands' not in data:
            data['commands'] = []

        if path not in self.context.data.get('commands'):
            data['commands'].append(path)

        self.context.update(data)

    def list(self):
        return self.context.data['commands']


class ContextPrompts:
    def __init__(self, context):
        self.context = context

    @functools.cached_property
    def path(self):
        path = self.context.path / 'history'
        path.mkdir(exist_ok=True, parents=True)
        return path

    def list(self):
        # Get list of files with their modification times
        files = [
            (f, os.path.getmtime(f))
            for f in Path(self.path).iterdir()
            if f.is_file()
        ]

        # Sort by modification time (most recent first)
        files.sort(key=lambda x: x[1], reverse=True)

        # Print files with their modification times
        return [file[0] for file in files]

    @property
    def latest(self):
        files = self.list()
        if files:
            with files[0].open('r') as f:
                return f.read()

    def add(self, prompt):
        _ = hashlib.new('sha1')
        _.update(prompt.encode('utf8'))
        path = self.path / _.hexdigest()
        if path.exists():
            return
        cli2.log.debug('writing prompt', path=path, prompt=prompt)
        with path.open('w') as f:
            f.write(prompt)

    def create_or_latest(self, prompt):
        if prompt:
            self.add(prompt)
            return prompt
        else:
            return self.latest


class Context:
    default_data = textwrap.dedent('''
        # List of file paths to attach to your prompts
        paths: []

        # List of commands to execute and attach output for
        commands: []

        # Test commands to do TDD on
        test_commands: []

        # List of plugins to enrich the context
        plugins:
        - inspect
    ''').strip()

    def __init__(self, project, path):
        self.project = project
        self.path = path
        self.paths = ContextPaths(self)
        self.commands = ContextCommands(self)
        self.prompts = ContextPrompts(self)

    @classmethod
    def current(cls, project):
        current = project.path / '.larbin/contexts/current'
        if current.exists():
            return cls.switch(project, current.readlink())
        else:
            return cls.switch(project, 'default')

    @classmethod
    def switch(cls, project, name):
        context_path = project.path / '.larbin/contexts'
        context_path.mkdir(exist_ok=True, parents=True)

        current = context_path / 'current'
        new = context_path / name

        if not new.exists():
            new.mkdir(exist_ok=True, parents=True)
        if current.exists():
            current.unlink()
        current.symlink_to(new)
        return cls(project, new)

    @property
    def name(self):
        return self.path.name

    @property
    def data_path(self):
        return self.path / 'data.yml'

    @property
    def data(self):
        if not self.data_path.exists():
            with self.data_path.open('w') as f:
                f.write(self.default_data)

        with self.data_path.open('r') as f:
            return yaml.safe_load(f.read())

    def update(self, **kwargs):
        data = self.data.copy()
        data.update(kwargs)
        with self.data_path.open('w') as f:
            f.write(yaml.dump(data))

    async def template(self):
        template = []

        data = self.data
        if paths := data.get('paths', []):
            statement = '{{ prompt2.contents(["'
            statement += '", "'.join([str(p) for p in paths])
            statement += '"]) }}'
            template.append(statement)
            print(cli2.t.g('INJECTED CONTENTS OF ') + ', '.join(paths))

        for command in data.get('commands', []):
            template.append('{{ cli2.shell("' + command + '") }}')
            print(cli2.t.g('INJECTED OUTPUT OF ') + command)

        for plugin in data.get('plugins', []):
            result = await self.plugins[plugin].template()
            if result:
                template += result

        if extra := data.get('content', ''):
            template += extra

        return '\n'.join(template)

    @functools.cached_property
    def plugins(self):
        plugins = dict()
        for plugin in importlib.metadata.entry_points(group='larbin'):
            try:
                plugins[plugin.name] = plugin.load()(self)
            except:
                cli2.log.exception(
                    f'Failed loading plugin',
                    name=plugin.name,
                    value=plugin.value,
                )
        return plugins

    def context_prompt(self, prompt=None):
        if prompt:
            prompt = ' '.join(prompt)
            self.update(prompt=prompt)
        elif self.data.get('prompt', None):
            prompt = self.data['prompt']
        else:
            prompt = cli2.editor('Type your prompt here')
            self.update(prompt=prompt)
        return prompt

    @property
    def plan(self):
        return self.path / 'plan.md'
