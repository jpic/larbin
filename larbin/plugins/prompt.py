import cli2
import larbin
import cli2
import prompt2
import typing as t


class PromptPlugin(larbin.Plugin):
    """
    A plugin to send a raw prompt to the AI for direct file modifications.

    This plugin bypasses the planning stage and directly asks the AI editor
    model to generate entire file contents based on the prompt and context.
    It uses the `larbin.wholefiles` parser to apply the changes.

    Note: This plugin currently lacks the `@cli2.cmd` decorator and might be
    intended for internal use or is incomplete as a user-facing command.
    The docstring below assumes it's intended as a command for illustrative
    purposes.
    """
    # Missing @cli2.cmd decorator if intended as a command
    async def prompt(self, *prompt: str):
        """
        Send a prompt directly to the AI for whole-file generation/modification.

        This command takes a prompt, combines it with the current context
        (including `LARBIN.md`), and asks the AI editor model to generate
        the complete content for the relevant files. The AI's response,
        expected in a format parsable by `larbin.wholefiles`, is used to
        overwrite existing files or create new ones. Use with caution, as it
        can lead to large, untested changes.

        Command-line specific usage (if decorator were present):
        The arguments passed on the command line form the prompt. If no
        arguments are given, it uses the latest prompt stored in the context.

        Example (if decorator were present):
            `larbin prompt rewrite main.py to use asyncio`

        Side Effects:
            - Creates a prompt record in the context.
            - Sends context and prompt to the AI.
            - **Overwrites or creates project files** based on the AI's response.
            - Prints status messages to the console.

        :param prompt: The prompt describing the desired file content or changes.
                       If empty, uses the latest prompt from the context.
        :type prompt: t.Tuple[str, ...]

        :raises ValueError: If no prompt is provided and none exists in the context.
        :raises: Potentially exceptions from ``prompt2.Model.__call__`` if the
                 AI request fails or the response format is invalid.
        :raises: Potentially exceptions from the parser's `apply` method during
                 file modification.
        """
        prompt_str = self.context.prompts.create_or_latest(' '.join(prompt))
        if not prompt_str:
            # Use ValueError for consistency, rather than printing directly
            raise ValueError('Pass a prompt argument, or ensure a previous prompt exists in the context.')

        # context = self.context.enrich(prompt_str) # enrich seems unused?

        prompt_obj = prompt2.Prompt(content=prompt_str)
        template_content = await self.context.template()
        if template_content:
             prompt_obj.content += ''.join(template_content)

        model = prompt2.Model('editor')
        result = await model(prompt_obj, 'larbin.wholefiles')
        # Assuming result.parser.apply exists and handles wholefiles format
        await result.parser.apply(result)

