"""
Run larbin hack to get started
"""

import cli2
import functools
import os
import shutil
import textwrap
from pathlib import Path

from larbin import project, context


"""
# commands are added by plugins
# inspect project (generate LARBIN.md)
larbin inspect
# change stuff in code
larbin prompt do something like that
# same, but with interactive plan making first, more efficient
larbin plan do something like that
# loop on a command
larbin tdd test command

# edit context YAML
larbin context edit
# add/show context files
larbin context file
# add/show context commands
larbin context command
# generate context template
larbin context template
# render context
larbin context render
# switch to another context
larbin context switch foo
# list project contexts
larbin context list

# generate repo map
larbin repo map
# scan project
larbin repo scan
# make a commit
larbin repo commit [files...]
~
"""

class ContextCommands:
    """
    Manage LLM contexts
    """
    def __init__(self, context):
        self.context = context

    @cli2.cmd
    def switch(self, name, *prompt):
        """
        Switch to another context

        :param name: context name
        :param prompt: prompt for context
        """
        context = self.context.switch(self.context.project, name)
        if prompt:
            context.update(prompt=' '.join(prompt))
        print(cli2.t.o.b('SWITCHED TO CONTEXT: ') + name)

    @cli2.cmd
    def prompt(self, *prompt):
        """
        Edit context prompt.

        :param prompt: Will use that from the command line
        """
        if prompt:
            prompt = ' '.join(prompt)
        else:
            if not cli2.confirm('Write a prompt now for this context?'):
                return
            prompt = cli2.editor()
        context.data.update(prompt=prompt)
        print(cli2.t.o.b('SAVED PROMPT'))
        print(prompt)

    @cli2.cmd(color='green')
    def template(self):
        """
        Generate the context template.
        """
        return self.context.template()

    @cli2.cmd(color='gray')
    def path(self):
        """
        Print context path
        """
        return str(self.context.data_path)

    @cli2.cmd(color='green')
    def show(self):
        """
        Show YAML context data
        """
        return self.context.data

    @cli2.cmd(color='yellow')
    def edit(self):
        """
        Edit the context data in YAML
        """
        if not self.context.data_path.exists():
            with self.context.data_path.open('w') as f:
                f.write(self.context.default_data)

        cli2.editor(path=self.context.data_path)

    @cli2.cmd(color='red')
    def reset(self):
        """ Reset current context """
        shutil.rmtree(self.context.path)
        print(cli2.t.r.b('CONTEXT RESET: ') + self.context.name)

    @cli2.cmd(color='green')
    def list(self):
        """ List project contexts """
        return {
            path.name: str(path)
            for path in self.context.path.parent.iterdir()
        }

    @cli2.cmd
    def archive(self, name):
        """
        Archive a context

        It will still show in the list command, but won't show in the CLI until
        next time you switch to it.

        :param name: Context name
        """
        path = self.path / name / 'archived'
        path.touch()


class ConsoleScript(cli2.Group):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        global context, project

        # Set initial docstring
        self.doc = __doc__

        # Load commands from plugins
        for plugin in context.plugins.values():
            self.load(plugin)

        # Create and load the 'context' subgroup
        ctx = self.group('context', doc=textwrap.dedent(f'''
            Manage contexts and switch context.

            Use `larbin context switch <name>` to change context.
        '''))
        ctx.load(ContextCommands(context))

        # Create and load the 'project' subgroup
        prj = self.group('project', doc='Manage project')
        prj.load(project)

        # Note: The dynamic parts (like showing current context) might need
        # adjustment if they were intended to be shown in --help output dynamically.
        # For now, we focus on making the structure discoverable by Sphinx.

    def __call__(self, *argv):
        global context
        # Update docstring dynamically before showing help, if needed
        # This might not be the best place if Sphinx needs the final docstring
        # during build time. Consider making the docstring more static or
        # finding another way if dynamic help content based on runtime state
        # is critical.
        ct = [
            cli2.t.y.b('CURRENT CONTEXT: ') + context.name,
            cli2.render(context.data),
        ]
        # Augmenting self.doc here might be too late for Sphinx
        self.doc = __doc__ + '\n' + '\n'.join(ct)

        return super().__call__(*argv)


class DBCommand(cli2.Command):
    def async_mode(self):
        return True

    async def async_call(self, *argv):
        await project.db.session_open()
        return await super().async_call(*argv)

    async def post_call(self):
        await project.db.session_close()


cli = ConsoleScript(cmdclass=DBCommand)
