import cli2
import larbin
import prompt2


import typing as t


class AutoContextPlugin(larbin.Plugin):
    """
    A plugin that uses AI to automatically determine relevant files for context.

    Based on a given prompt and the symbols present in the repository, this
    plugin queries an AI model to identify which files should be included
    in the context for subsequent operations.
    """
    @cli2.cmd
    async def autocontext(self, *prompt: str):
        """
        Automatically select context files based on the prompt and repo symbols.

        This command asks the AI to identify relevant files for a given task
        described in the prompt. It analyzes the prompt and the repository's
        symbol map to suggest files, which are then added to the current
        context.

        Command-line specific usage:
        The arguments passed on the command line form the prompt. If no
        arguments are given, it uses the latest prompt stored in the context.

        Example:
            `larbin autocontext refactor the user authentication module`

        Side Effects:
            - Modifies `self.context.paths` by adding the identified files.
            - Prints the new context information to the console.

        :param prompt: The prompt describing the task. If empty, uses the
                       latest prompt from the context.
        :type prompt: t.Tuple[str, ...]

        :raises: Potentially exceptions from ``prompt2.Model.__call__`` if the
                 AI request fails.
        """
        prompt_str = self.context.context_prompt(prompt)

        prompt_obj = prompt2.Prompt('larbin.autocontext', prompt=prompt_str)
        model = prompt2.Model(['autocontext', 'architect'])

        print(cli2.t.g.b('GENERATING CONTEXT'))
        result = await model(prompt_obj, 'larbin.pathlist')
        self.context.paths.add(*result)
        print(cli2.t.g.b('NEW CONTEXT:'))
        cli2.print(self.context.data)
