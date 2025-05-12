import cli2
import larbin
import prompt2


import typing as t


class AskPlugin(larbin.Plugin):
    """
    A plugin to ask general questions to the AI based on the current context.

    This plugin sends a user's query along with project context to an AI
    model and streams the response without modifying any project files.
    """
    @cli2.cmd
    async def ask(self, *prompt: str, _cli2=None):
        """
        Ask the AI a question related to the project or general programming.

        This command sends your question, combined with the current project
        context (files, symbols, etc.), to the AI for an explanation or
        answer. The response is streamed directly to the console. It does
        not modify any files in the project.

        Command-line specific usage:
        The arguments passed on the command line form the prompt.

        Example:
            `larbin ask how to implement a context manager in Python`

        :param prompt: The question or prompt to ask the AI. Consists of all
                       command line arguments joined together.
        :type prompt: t.Tuple[str, ...]
        :param _cli2: Internal cli2 context object (unused by user).
        :type _cli2: cli2.Context, optional

        :raises: Potentially exceptions from ``prompt2.Model.__call__`` if the
                 AI request fails.
        """
        prompt_str = ' '.join(prompt)
        if not prompt_str:
            return _cli2.help(

                error='Pass some prompt, ie. `larbin ask how to do this`',
            )

        prompt = prompt2.Prompt('larbin.ask', prompt=' '.join(prompt))
        prompt.content += '\n' + await self.context.template()
        model = prompt2.Model(['ask', 'architect'])
        print(cli2.t.o.b('GENERATING EXPLANATION') + f' with {model}')
        await model(prompt, stream=True)
