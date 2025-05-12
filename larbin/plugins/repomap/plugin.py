import cli2
import larbin

from . import scan_dir, scan_files, repo_map


from . import scan_dir, scan_files, repo_map


class RepoMapPlugin(larbin.Plugin):
    """
    A plugin to scan the repository and generate a symbol map.

    This plugin analyzes the project's codebase to identify key symbols
    (classes, functions, variables), their relationships (imports), and
    generates a structured representation (repo map) of the project.
    This map can be used by other plugins or the AI to better understand
    the project structure.
    """
    @cli2.cmd(color='green')
    async def repomap(self) -> str:
        """
        Scan the repository, analyze symbols and imports, and generate a repo map.

        This command performs a multi-stage analysis:
        1. Scans the project directory to index code symbols using
           :class:`~.scan_dir.CodeIndexer`.
        2. Analyzes import statements to understand dependencies using
           :class:`~.scan_files.ImportAnalyzer`.
        3. Generates a textual representation of the repository structure and
           symbols using :class:`~.repo_map.RepoMapGenerator`.

        Command-line specific usage:
        Takes no arguments. The generated map string is returned but also
        typically stored or used internally by the context.

        Example:
            `larbin repomap`

        Side Effects:
            - Reads project files extensively.
            - Performs CPU-intensive analysis.
            - May store analysis results internally (e.g., caching).
            - Prints status messages to the console.

        :return: A string containing the generated repository map.
        :rtype: str

        :raises: Potential exceptions related to file system access, code parsing
                 errors during indexing or analysis.
        """
        print(cli2.t.o.b('SCANNING PROJECT SYMBOLS'))
        dir_indexer = scan_dir.CodeIndexer(self.project)
        paths = await dir_indexer.index_repo_async()
        print(cli2.t.o.b('ANALYZING IMPORTS'))
        import_analyzer = scan_files.ImportAnalyzer(self.project, paths, 'python')
        await import_analyzer.analyze_and_store_imports()
        print(cli2.t.o.b('GENERATING REPO MAP'))
        map_generator = repo_map.RepoMapGenerator(self.project)
        repo_map_string = await map_generator.get_map_string()
        # Consider printing the map or saving it, currently just returns
        # print(repo_map_string)
        return repo_map_string

