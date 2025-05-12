import cli2
import larbin
import difflib
import os
import textwrap
from prompt2 import parser
from pathlib import Path


class SearchReplaceParser(parser.Parser):
    system = textwrap.dedent('''
        You are an automated coding assistant tasked with modifying files based on user instructions. Your response must consist only of search/replace edit blocks in the exact format below, with no additional text, explanations, or whole-file content outside this format. Each edit block must target a single file and include a relative path (relative to the project root) specified in a line starting with EDIT BLOCK FOR <relative/path/to/file>, followed by a code block wrapped in triple backticks (```) containing the code to be replaced and the new code to insert. Within the code block, use single-line markers `<<<<SEARCH` to indicate the start of the code to be replaced and `<<<<REPLACE` to indicate the start of the new code to insert. The `EDIT BLOCK FOR` line *must* be outside the triple backticks and must not appear in the code block. The file extension must match the programming language (e.g., .py for Python, .js for JavaScript). If the user does not provide a path or filename, infer a relative path (e.g., src/<filename>) and filename based on the task, and add a comment in the code after `<<<<REPLACE` noting the inferred path. If the language is unclear, default to Python. Every edit block *must* have a preceding `EDIT BLOCK FOR` line with a relative path. Outputting whole files, diff blocks, or any other format will crash the system. Ensure the code after `<<<<SEARCH` matches the existing file content exactly, and the code after `<<<<REPLACE` is syntactically correct. If no file changes are needed, output nothing.

        Output format:

        EDIT BLOCK FOR src/file1.py
        ```python
        <<<<SEARCH
        <exact code to be replaced>
        <<<<REPLACE
        <new code to insert>
        ```

        EDIT BLOCK FOR scripts/file2.js
        ```javascript
        <<<<SEARCH
        <exact code to be replaced>
        <<<<REPLACE
        <new code to insert>
        ```
    ''')

    def parse(self, response):
        edits = []
        current_path = None
        current_block = {'search': [], 'replace': [], 'lang': None}
        mode = None  # 'search' or 'replace'

        for line in response.splitlines():
            if line.startswith('EDIT BLOCK FOR'):
                if current_path and current_block['search'] and current_block['replace']:
                    edits.append({
                        'path': current_path,
                        'search': '\n'.join(current_block['search']),
                        'replace': '\n'.join(current_block['replace']),
                        'lang': current_block['lang']
                    })
                current_path = line.split()[-1]
                current_block = {'search': [], 'replace': [], 'lang': None}
                mode = None
                continue
            if line.strip().startswith('```'):
                lang = line.strip()[3:] or 'python'  # Default to python if no lang specified
                current_block['lang'] = lang
                continue
            if line.strip() == '<<<<SEARCH':
                mode = 'search'
                continue
            if line.strip() == '<<<<REPLACE':
                mode = 'replace'
                continue
            if current_path and mode:
                if mode == 'replace':
                    current_block['replace'].append(line)
                elif mode == 'search':
                    current_block['search'].append(line)

        # Append the last block if it exists
        if current_path and current_block['search'] and current_block['replace']:
            edits.append({
                'path': current_path,
                'search': '\n'.join(current_block['search']),
                'replace': '\n'.join(current_block['replace']),
                'lang': current_block['lang']
            })

        return edits

    def path_fix(self, path_str):
        # LLMs might eat paths, esoteric solution
        if os.path.exists(path_str):
            return path_str

        possible = []
        for project_file in project_files:
            if str(project_file).endswith(path_str):
                possible.append(project_file)
        if len(possible) == 1:
            path_str = possible[0]
        elif possible:
            path_str = cli2.closest_path(path_str, possible)
        else:
            path_str = cli2.closest_path(path_str, project_files)
        return path_str

    async def apply(self, result):
        for edit in result:
            path_str = self.path_fix(edit['path'])
            with open(path_str, 'r') as f:
                old_text = f.read()

            # Generate unified diff
            new_text = old_text.replace(edit['search'], edit['replace'], 1)
            diff = difflib.unified_diff(
                old_text.splitlines(),
                new_text.splitlines(),
                fromfile=str(path_str),
                tofile=str(path_str),
                lineterm='',
            )

            # Display diff using cli2.diff
            cli2.diff(diff)

            # Ask for confirmation
            if not self.apply_diff():
                continue

            # Apply the replacement
            with open(path_str, 'w') as f:
                f.write(new_text)

    def apply_diff(self):
        if getattr(self, 'apply_always', False):
            return True
        result = cli2.choice(
            'Apply diff? (A for Always/Auto)',
            ['y', 'n', 'a'],
        )
        if result == 'a':
            self.apply_always = True
            return True
        return result == 'y'


class WholefilesParser(parser.Parser):
    system = textwrap.dedent("""
        You are an automated coding assistant tasked with creating or modifying files based on user instructions. Your response must consist only of file operations in the exact format below, with no additional text, explanations, code, or diff blocks outside this format:

        FILE CONTENT FOR src/file1.py
        ```python
        <complete content of file1>
        ```

        FILE CONTENT FOR scripts/file2.js
        ```javascript
        <complete content of file2>
        ```
    """)  # noqa

    def parse(self, response):
        files = dict()
        for line in response.splitlines():
            if line.startswith('FILE CONTENT FOR'):
                current_path = line.split()[-1]
                files[current_path] = []
            elif line.strip().startswith('```'):
                continue
            else:
                try:
                    files[current_path].append(line)
                except UnboundLocalError:
                    breakpoint()
        return {name: '\n'.join(value) for name, value in files.items()}

    def path_fix(self, path_str):
        # LLMs might eat paths, esotheric solution
        if os.path.exists(path_str):
            return path_str

        possible = []
        for project_file in project_files:
            if str(project_file).endswith(path_str):
                possible.append(project_file)
        if len(possible) == 1:
            path_str = possible[0]
        elif possible:
            path_str = cli2.closest_path(path_str, possible)
        else:
            path_str = cli2.closest_path(path_str, project_files)
        return path_str

    async def apply(self, result):
        for path_str, new_text in result.items():
            with open(path_str, 'r') as f:
                old_text = f.read()

            if old_text == new_text:
                continue

            diff = difflib.unified_diff(
                old_text.split('\n'),
                new_text.split('\n'),
                fromfile=str(path_str),
                tofile=str(path_str),
                lineterm='',
            )

            cli2.diff(diff)
            if not self.apply_diff():
                return

            with open(path_str, 'w') as f:
                f.write(new_text)

    def apply_diff(self):
        if getattr(self, 'apply_always', False):
            return True
        result = cli2.choice(
            'Apply diff? (A for Always/Auto)',
            ['y', 'n', 'a'],
        )
        if result == 'a':
            self.apply_always = True
            return True
        return result == 'y'


class DiffMarkdownParser(parser.Parser):
    system = """
Make a structured reply, you can use ```diff blocks for changing file contents with unified diff format
    """  # noqa

    def parse(self, response):
        from markdown_it import MarkdownIt
        from larbin import diff, project
        # Import the new function
        from larbin.diff import run_parse_fix_parse

        md = MarkdownIt()
        parsed_diffs = []  # Initialize a list to hold results
        # Ensure project files are loaded (assuming project instance is `project.project`)
        project_files_set = set(str(p) for p in larbin.project.project.files)

        for token in md.parse(response):
            if token.type == "fence" and "diff" in token.info:
                diff_content = token.content
                # Call the new function to parse and fix the diff
                diffs = run_parse_fix_parse(diff_content, project_files_set)
                parsed_diffs.extend(diffs)  # Add the parsed diffs to our list

        # Return the list of DiffFile objects
        return parsed_diffs


class PathList(parser.List):
    system = """
You are a coding assistant program. Your response must be structured to avoid crashing the program. Reply **only** with a list of file paths relevant to the context and which exist in the context, specify them exactly as you see them in the context. Do not try to guess any path.
Each file path must be on a new line preceded by a hyphen and a space and ordered by relevance. Include only the paths, followed by a space and some brief explanation on a single line.

**Response format:**
- ./path/to/file1 because ...
- path/to/file2 so that ...
- /path/to/file3 which might contain ...
"""  # noqa

    def parse(self, response):
        result = super().parse(response)
        return [
            token.strip('`')
            for token in response.split()
            if os.path.exists(token)
            or os.path.exists(token.strip('`'))
        ]


def paths():
    return [Path(__file__).parent / 'templates']
