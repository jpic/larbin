from dataclasses import dataclass, field
from typing import List, Optional, Set, Dict
import re
from abc import ABC, abstractmethod

# Assuming cli2 is available with closest and closest_path
try:
    from cli2 import closest, closest_path
except ImportError:
    # Provide dummy implementations if cli2 is not available
    def closest(value, possibilities): return min(possibilities) if possibilities else None
    def closest_path(value, possibilities): return min(possibilities) if possibilities else None

# Token types for the lexer
class TokenType:
    FILE_HEADER = "FILE_HEADER"
    HUNK_HEADER = "HUNK_HEADER"
    LINE_ADDED = "LINE_ADDED"
    LINE_REMOVED = "LINE_REMOVED"
    LINE_CONTEXT = "LINE_CONTEXT"
    NO_NEWLINE = "NO_NEWLINE"
    ERROR = "ERROR"

# Base error class (forward declaration for Token)
class ParseError(ABC):
    pass

@dataclass
class Token:
    type: str
    value: str
    line_number: int
    errors: List['ParseError'] = field(default_factory=list)

@dataclass
class DiffLine:
    content: str
    type: str
    line_number: int

@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: List[DiffLine]
    failed: bool = False  # Flag to mark if hunk application failed

    def to_string(self) -> str:
        """
        Generate a unified diff string for this hunk.

        Returns:
            A string representing the hunk in unified diff format.
        """
        output_lines = []

        # Construct hunk header: @@ -old_start,old_count +new_start,new_count @@
        old_range = f"{self.old_start},{self.old_count}" if self.old_count > 0 else f"{self.old_start},0"
        new_range = f"{self.new_start},{self.new_count}" if self.new_count > 0 else f"{self.new_start},0"
        output_lines.append(f"@@ -{old_range} +{new_range} @@")

        # Add diff lines
        for line in self.lines:
            if line.type == TokenType.LINE_ADDED:
                output_lines.append(f"+{line.content}")
            elif line.type == TokenType.LINE_REMOVED:
                output_lines.append(f"-{line.content}")
            elif line.type == TokenType.LINE_CONTEXT:
                output_lines.append(f" {line.content}")
            elif line.type == TokenType.NO_NEWLINE:
                output_lines.append(line.content)  # e.g., "\ No newline at end of file"

        return '\n'.join(output_lines)

    def apply(self, source_lines: List[str]) -> List[str]:
        """
        Apply this hunk to the source file content, marking as failed if unappliable.

        Args:
            source_lines: List of strings representing the source file's lines.

        Returns:
            List of strings representing the modified file lines.
            If the hunk is unappliable, sets self.failed to True and returns source_lines unchanged.
        """
        # Reset failed flag
        self.failed = False
        result_lines = source_lines.copy()

        old_start = self.old_start - 1  # Convert to 0-based indexing
        old_count = self.old_count

        # Validate context lines
        expected_context = [line.content for line in self.lines
                           if line.type in (TokenType.LINE_REMOVED, TokenType.LINE_CONTEXT)]
        context_start = old_start
        context_end = context_start + old_count

        # Check if the range is valid
        if context_start < 0 or context_end > len(source_lines):
            self.failed = True
            return source_lines

        # Compare context lines
        actual_context = source_lines[context_start:context_end]
        if expected_context != actual_context:
            self.failed = True
            return source_lines

        # Apply the hunk: remove old lines, insert new lines
        insert_lines = [line.content for line in self.lines
                        if line.type in (TokenType.LINE_ADDED, TokenType.LINE_CONTEXT)]

        # Remove old lines and insert new ones
        result_lines[context_start:context_end] = insert_lines

        return result_lines

@dataclass
class DiffFile:
    old_path: Optional[str]
    new_path: Optional[str]
    hunks: List[Hunk]

    def to_string(self) -> str:
        """
        Generate a unified diff string for this DiffFile.

        Returns:
            A string representing the file diff in unified diff format.
        """
        output_lines = []

        # Add file headers
        old_path = self.old_path if self.old_path else 'a/unknown'
        new_path = self.new_path if self.new_path else 'b/unknown'
        old_header_path = old_path if old_path != 'a/dev/null' else '/dev/null'
        new_header_path = new_path if new_path != 'b/dev/null' else '/dev/null'
        output_lines.append(f"--- {old_header_path}")
        output_lines.append(f"+++ {new_header_path}")

        # Add hunks
        for hunk in self.hunks:
            output_lines.append(hunk.to_string())

        return '\n'.join(output_lines) + '\n'

    def apply(self, file_contents: Dict[str, str]) -> Dict[str, str]:
        """
        Apply this DiffFile's hunks to the file contents.

        Args:
            file_contents: Dictionary mapping file paths to their text content.

        Returns:
            Updated dictionary with modified file contents.
            Marks hunks as failed if they cannot be applied.
        """
        modified_contents = file_contents.copy()

        # Handle file deletion
        if self.new_path == 'b/dev/null':
            if self.old_path in modified_contents:
                del modified_contents[self.old_path]
            return modified_contents

        # Handle file creation
        if self.old_path == 'a/dev/null':
            source_lines = []
        else:
            source_content = modified_contents.get(self.old_path, '')
            source_lines = source_content.splitlines()

        # Apply each hunk
        result_lines = source_lines
        current_offset = 0

        for hunk in self.hunks:
            # Adjust hunk start lines based on offset
            original_old_start = hunk.old_start
            hunk.old_start += current_offset
            modified_lines = hunk.apply(result_lines)

            if hunk.failed:
                # Restore original start line and continue
                hunk.old_start = original_old_start
                continue

            # Update result lines and offset
            old_count = hunk.old_count
            new_lines = [line.content for line in hunk.lines
                         if line.type in (TokenType.LINE_ADDED, TokenType.LINE_CONTEXT)]
            result_lines = modified_lines
            current_offset += len(new_lines) - old_count

        # Store modified content
        modified_content = '\n'.join(result_lines)
        if source_lines and not source_lines[-1].endswith('\n') and not any(
            line.type == TokenType.NO_NEWLINE for hunk in self.hunks for line in hunk.lines
        ):
            modified_content += '\n'

        modified_contents[self.new_path] = modified_content

        # Handle file rename/move
        if self.old_path != self.new_path and self.old_path in modified_contents and self.old_path != 'a/dev/null':
            del modified_contents[self.old_path]

        return modified_contents

# Base error class definition
class ParseError(ABC):
    def __init__(self, line_number: int, details: Optional[str] = None):
        self.line_number = line_number
        self.details = details

    @abstractmethod
    def fix(self, context: dict) -> Optional[dict]:
        pass

    @abstractmethod
    def message(self) -> str:
        pass

    def __repr__(self):
        return f"{self.__class__.__name__}(line={self.line_number}, details='{self.details}')"

    def __eq__(self, other):
        if not isinstance(other, ParseError):
            return NotImplemented
        return (self.__class__ == other.__class__ and
                self.line_number == other.line_number)

    def __hash__(self):
        return hash((self.__class__, self.line_number))

# Specific error classes
class EmptyInputError(ParseError):
    def message(self) -> str:
        return "Empty input"

    def fix(self, context: dict) -> Optional[dict]:
        return None

class UnrecognizedLineError(ParseError):
    def message(self) -> str:
        return f"Unrecognized line format: {self.details}"

    def fix(self, context: dict) -> Optional[dict]:
        token: Token = context.get('token')
        if not token: return None

        value = token.value
        hunk_match = re.match(r"@@\s*-([\da-zA-Z]+(?:,[\d]+)?)\s*\+([\da-zA-Z]+(?:,[\d]+)?)\s*@@.*", value)
        if hunk_match:
            def sanitize_hunk_part(part):
                parts = part.split(',')
                start_str = parts[0]
                count_str = parts[1] if len(parts) > 1 else '1'
                try: start_num = int(start_str)
                except ValueError: start_num = 1
                try: count_num = int(count_str)
                except ValueError: count_num = 0
                start_num = max(1, start_num)
                count_num = max(0, count_num)
                return start_num, count_num

            old_start, old_count = sanitize_hunk_part(hunk_match.group(1))
            new_start, new_count = sanitize_hunk_part(hunk_match.group(2))

            token.type = TokenType.HUNK_HEADER
            token.value = f"@@ -{old_start},{old_count} +{new_start},{new_count} @@"
            token.errors = [e for e in token.errors if not isinstance(e, UnrecognizedLineError)]
            return context

        if value.startswith(('+', '-', ' ')):
            line_content = value[1:]
            prefix = value[0]
        else:
            line_content = value
            prefix = ' '

        token.type = TokenType.LINE_CONTEXT
        token.value = prefix + line_content
        token.errors = [e for e in token.errors if not isinstance(e, UnrecognizedLineError)]
        return context

class MissingFileHeaderError(ParseError):
    def message(self) -> str:
        return "Expected file header ('---' or '+++')"

    def fix(self, context: dict) -> Optional[dict]:
        tokens: List[Token] = context.get('tokens')
        current_index: int = context.get('current')
        if not tokens or current_index is None:
            if self.line_number == 1 and current_index == 0:
                default_old = Token(TokenType.FILE_HEADER, "--- a/unknown", 0, [])
                default_new = Token(TokenType.FILE_HEADER, "+++ b/unknown", 0, [])
                new_tokens = [default_old, default_new] + tokens
                context['tokens'] = new_tokens
                context['list_modified'] = True
                if tokens:
                    original_first_token = tokens[0]
                    original_first_token.errors = [e for e in original_first_token.errors if not isinstance(e, MissingFileHeaderError)]
                return context
            else:
                return None

        error_token = tokens[current_index]
        is_at_start = True
        for i in range(current_index):
            if tokens[i].type == TokenType.FILE_HEADER and tokens[i].value.startswith("---"):
                is_at_start = False
                break

        if is_at_start:
            default_old = Token(TokenType.FILE_HEADER, "--- a/unknown", 0, [])
            if error_token.type == TokenType.FILE_HEADER and error_token.value.startswith("+++"):
                error_token.errors = [e for e in error_token.errors if not isinstance(e, MissingFileHeaderError)]
                new_tokens = tokens[:current_index] + [default_old] + tokens[current_index:]
            else:
                default_new = Token(TokenType.FILE_HEADER, "+++ b/unknown", 0, [])
                error_token.errors = [e for e in error_token.errors if not isinstance(e, MissingFileHeaderError)]
                new_tokens = tokens[:current_index] + [default_old, default_new] + tokens[current_index:]

            context['tokens'] = new_tokens
            context['list_modified'] = True
            return context
        else:
            error_token.errors = [e for e in error_token.errors if not isinstance(e, MissingFileHeaderError)]
            return context

class InvalidFileHeaderError(ParseError):
    def message(self) -> str:
        return f"Invalid file header format: {self.details}"

    def fix(self, context: dict) -> Optional[dict]:
        token: Token = context.get('token')
        if not token or not token.value:
            return None
        value = token.value.strip()
        prefix = None
        if value.startswith('---'):
            prefix = '---'
        elif value.startswith('+++'):
            prefix = '+++'

        if prefix:
            path = value[len(prefix):].strip() or 'unknown'
            if path != 'unknown' and not path.startswith(('a/', 'b/')):
                path = ('a/' if prefix == '---' else 'b/') + path
            token.value = f"{prefix} {path}"
            token.errors = [e for e in token.errors if not isinstance(e, InvalidFileHeaderError)]
            token.errors = [e for e in token.errors if not isinstance(e, EmptyFilePathError)]
            return context
        else:
            return None

class EmptyFilePathError(ParseError):
    def message(self) -> str:
        return "Empty file path in header"

    def fix(self, context: dict) -> Optional[dict]:
        token: Token = context.get('token')
        available_paths: Set[str] = context.get('available_paths', set())
        if not token:
            return None
        prefix = '---' if token.value.startswith('---') else '+++'
        path_prefix = 'a/' if prefix == '---' else 'b/'
        default_path_final = path_prefix + 'unknown'
        chosen_path = default_path_final

        if available_paths:
            relevant_paths = {p for p in available_paths if p.startswith(path_prefix)}
            if relevant_paths:
                guessed_path = None
                try:
                    guessed_path = closest_path(path_prefix, relevant_paths)
                except Exception:
                    pass

                if guessed_path and guessed_path in relevant_paths:
                    chosen_path = guessed_path
                else:
                    if relevant_paths:
                        chosen_path = min(relevant_paths)

        token.value = f"{prefix} {chosen_path}"
        token.errors = [e for e in token.errors if not isinstance(e, EmptyFilePathError)]
        token.errors = [e for e in token.errors if not isinstance(e, InvalidFileHeaderError)]
        return context

class NoHunksError(ParseError):
    def message(self) -> str:
        return "No valid hunks found for file"

    def fix(self, context: dict) -> Optional[dict]:
        token: Token = context.get('token')
        tokens: List[Token] = context.get('tokens')
        current_token_index: int = context.get('current')
        if not token or not tokens or current_token_index is None:
            return None

        file_start_index = -1
        if token.type == TokenType.FILE_HEADER and token.value.startswith("---"):
            file_start_index = current_token_index
        else:
            try:
                error_token_index = -1
                for idx, t in enumerate(tokens):
                    if t is token:
                        error_token_index = idx
                        break
                if error_token_index == -1: error_token_index = current_token_index
            except ValueError:
                error_token_index = current_token_index

            for i in range(error_token_index, -1, -1):
                if tokens[i].type == TokenType.FILE_HEADER and tokens[i].value.startswith("---"):
                    file_start_index = i
                    break
        if file_start_index == -1: return None

        insert_pos = file_start_index + 1
        if (insert_pos < len(tokens) and
            tokens[insert_pos].type == TokenType.FILE_HEADER and
            tokens[insert_pos].value.startswith("+++")):
            insert_pos += 1

        file_end_index = len(tokens)
        for i in range(insert_pos, len(tokens)):
            if tokens[i].type == TokenType.FILE_HEADER and tokens[i].value.startswith("---"):
                file_end_index = i
                break

        hunk_header_found = False
        for i in range(insert_pos, file_end_index):
            if tokens[i].type == TokenType.HUNK_HEADER:
                hunk_header_found = True
                break

        original_error_token = token
        original_error_token.errors = [e for e in original_error_token.errors if not isinstance(e, NoHunksError)]
        original_error_token.errors = [e for e in original_error_token.errors if not isinstance(e, EmptyHunkError)]

        if hunk_header_found:
            return context

        prev_token_line = tokens[insert_pos - 1].line_number if insert_pos > 0 else 0
        line_num = prev_token_line + 1
        hunk_token = Token(TokenType.HUNK_HEADER, "@@ -1,1 +1,1 @@", line_num, [])
        default_line = Token(TokenType.LINE_CONTEXT, " ", line_num + 1, [])

        if insert_pos > len(tokens): insert_pos = len(tokens)
        new_tokens = tokens[:insert_pos] + [hunk_token, default_line] + tokens[insert_pos:]

        context['tokens'] = new_tokens
        context['list_modified'] = True
        return context

def _sanitize_hunk_part(part_str: str) -> tuple[int, int]:
    parts = part_str.split(',')
    start_str = parts[0]
    count_str = parts[1] if len(parts) > 1 else '1'

    try:
        start_num = int(start_str)
        if start_num < 0:
            start_num = 1
    except ValueError:
        start_num = 1

    start_num = max(1, start_num)

    try:
        count_num = int(count_str)
        if count_num < 0:
            count_num = 0
    except ValueError:
        count_num = 0

    return start_num, count_num

class InvalidHunkHeaderError(ParseError):
    def message(self) -> str:
        return f"Invalid hunk header format: {self.details}"

    def fix(self, context: dict) -> Optional[dict]:
        token: Token = context.get('token')
        if not token: return None

        value = token.value
        hunk_match = re.match(r"@@\s*-([,\d\w-]+)\s*\+([,\d\w-]+)\s*@@.*", value)
        if hunk_match:
            old_part = hunk_match.group(1)
            new_part = hunk_match.group(2)
            old_start, old_count = _sanitize_hunk_part(old_part)
            new_start, new_count = _sanitize_hunk_part(new_part)

            token.value = f"@@ -{old_start},{old_count} +{new_start},{new_count} @@"
            token.errors = [e for e in token.errors if not isinstance(e, (InvalidHunkHeaderError, InvalidHunkNumbersError))]
            return context
        else:
            token.value = "@@ -1,0 +1,0 @@"
            token.errors = [e for e in token.errors if not isinstance(e, (InvalidHunkHeaderError, InvalidHunkNumbersError))]
            return context

class InvalidHunkNumbersError(ParseError):
    def message(self) -> str:
        return f"Invalid hunk numbers (e.g., negative, non-digit): {self.details}"

    def fix(self, context: dict) -> Optional[dict]:
        token: Token = context.get('token')
        if not token: return None

        hunk_match = re.match(r"@@\s*-([,\d\w-]+)\s*\+([,\d\w-]+)\s*@@.*", token.value)
        if hunk_match:
            old_part = hunk_match.group(1)
            new_part = hunk_match.group(2)
            old_start, old_count = _sanitize_hunk_part(old_part)
            new_start, new_count = _sanitize_hunk_part(new_part)
            token.value = f"@@ -{old_start},{old_count} +{new_start},{new_count} @@"
            token.errors = [e for e in token.errors if not isinstance(e, (InvalidHunkHeaderError, InvalidHunkNumbersError))]
            return context
        else:
            token.value = "@@ -1,0 +1,0 @@"
            token.errors = [e for e in token.errors if not isinstance(e, (InvalidHunkHeaderError, InvalidHunkNumbersError))]
            return context

class HunkLineCountMismatchError(ParseError):
    def message(self) -> str:
        return f"Hunk line count mismatch: {self.details}"

    def fix(self, context: dict) -> Optional[dict]:
        token: Token = context.get('token')
        tokens: List[Token] = context.get('tokens')
        current_hunk_header_index: int = context.get('current')
        if not token or token.type != TokenType.HUNK_HEADER or not tokens or current_hunk_header_index is None:
            return None

        i = current_hunk_header_index + 1
        actual_old_count = 0
        actual_new_count = 0
        while i < len(tokens):
            line_token = tokens[i]
            if line_token.type in (TokenType.HUNK_HEADER, TokenType.FILE_HEADER):
                break
            if line_token.type in (TokenType.LINE_REMOVED, TokenType.LINE_CONTEXT):
                actual_old_count += 1
            if line_token.type in (TokenType.LINE_ADDED, TokenType.LINE_CONTEXT):
                actual_new_count += 1
            if line_token.type == TokenType.ERROR:
                actual_old_count += 1
                actual_new_count += 1
            i += 1

        match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", token.value)
        if match:
            old_start = int(match.group(1))
            new_start = int(match.group(3))
            token.value = f"@@ -{old_start},{actual_old_count} +{new_start},{actual_new_count} @@"
            token.errors = [e for e in token.errors if not isinstance(e, HunkLineCountMismatchError)]
            return context
        else:
            token.errors = [e for e in token.errors if not isinstance(e, HunkLineCountMismatchError)]
            return context

class EmptyHunkError(ParseError):
    def message(self) -> str:
        return "Hunk contains no lines"

    def fix(self, context: dict) -> Optional[dict]:
        token: Token = context.get('token')
        tokens: List[Token] = context.get('tokens')
        current_hunk_header_index: int = context.get('current')
        if not token or token.type != TokenType.HUNK_HEADER or not tokens or current_hunk_header_index is None:
            return None

        line_num = token.line_number + 1
        default_line = Token(TokenType.LINE_CONTEXT, " ", line_num, [])
        insert_pos = current_hunk_header_index + 1
        if insert_pos > len(tokens): insert_pos = len(tokens)
        new_tokens = tokens[:insert_pos] + [default_line] + tokens[insert_pos:]

        match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", token.value)
        if match:
            old_start = int(match.group(1))
            new_start = int(match.group(3))
            token.value = f"@@ -{old_start},1 +{new_start},1 @@"
        else:
            token.value = f"@@ -1,1 +1,1 @@"

        token.errors = [e for e in token.errors if not isinstance(e, EmptyHunkError)]
        token.errors = [e for e in token.errors if not isinstance(e, HunkLineCountMismatchError)]

        context['tokens'] = new_tokens
        context['list_modified'] = True
        return context

class NoTokensError(ParseError):
    def message(self) -> str:
        return "No tokens provided to parser"

    def fix(self, context: dict) -> Optional[dict]:
        return None

# Lexer class
class DiffLexer:
    def __init__(self, text: str):
        self.lines = text.splitlines() if text else []
        self.current_line_index = 0
        self.line_number = 0

    def tokenize(self) -> List[Token]:
        tokens = []
        if not self.lines:
            return tokens

        while self.current_line_index < len(self.lines):
            line = self.lines[self.current_line_index]
            self.line_number += 1
            token = self._match_token(line)
            if token:
                tokens.append(token)
            self.current_line_index += 1
        return tokens

    def _match_token(self, line: str) -> Optional[Token]:
        patterns = [
            (r"^---(?:\s+.*)?$", TokenType.FILE_HEADER),
            (r"^\+\+\+(?:\s+.*)?$", TokenType.FILE_HEADER),
            (r"^@@\s*-.*?\s*\+.*?\s*@@.*$", TokenType.HUNK_HEADER),
            (r"^\+.*", TokenType.LINE_ADDED),
            (r"^-.*", TokenType.LINE_REMOVED),
            (r"^ .*", TokenType.LINE_CONTEXT),
            (r"^\\ No newline at end of file$", TokenType.NO_NEWLINE),
        ]

        for pattern, token_type in patterns:
            if re.match(pattern, line):
                errors = []
                stripped_line = line.rstrip('\r\n')
                if token_type == TokenType.FILE_HEADER:
                    prefix_len = 3
                    path = stripped_line[prefix_len:].strip()
                    if not path and stripped_line.strip() not in ['---', '+++']:
                        errors.append(EmptyFilePathError(self.line_number, f"{line[:3]} header has empty path but invalid format"))
                elif token_type == TokenType.HUNK_HEADER:
                    strict_match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", stripped_line)
                    if strict_match:
                        try:
                            old_start = int(strict_match.group(1))
                            old_count = int(strict_match.group(2) or '1')
                            new_start = int(strict_match.group(3))
                            new_count = int(strict_match.group(4) or '1')
                            if old_start <= 0 or old_count < 0 or new_start <= 0 or new_count < 0:
                                errors.append(InvalidHunkNumbersError(self.line_number, f"Invalid numbers in: {stripped_line}"))
                        except ValueError:
                            errors.append(InvalidHunkNumbersError(self.line_number, f"Non-integer numbers in: {stripped_line}"))
                    else:
                        errors.append(InvalidHunkHeaderError(self.line_number, f"Invalid format: {stripped_line}"))
                        lenient_match = re.match(r"@@\s*-([,\d\w-]+)\s*\+([,\d\w-]+)\s*@@.*", stripped_line)
                        if lenient_match:
                            old_part = lenient_match.group(1)
                            new_part = lenient_match.group(2)
                            try:
                                def contains_invalid_chars(part):
                                    if not re.fullmatch(r"-?\d+(,-?\d+)?", part):
                                        return True
                                    parts = part.split(',')
                                    if len(parts) > 1 and int(parts[1]) < 0:
                                        return True
                                    if int(parts[0]) <= 0:
                                        if len(parts) == 1 or int(parts[1]) != 0:
                                            return True
                                    return False

                                if contains_invalid_chars(old_part) or contains_invalid_chars(new_part):
                                    if not any(isinstance(e, InvalidHunkNumbersError) for e in errors):
                                        errors.append(InvalidHunkNumbersError(self.line_number, f"Invalid numbers in: {stripped_line}"))
                            except Exception:
                                if not any(isinstance(e, InvalidHunkNumbersError) for e in errors):
                                    errors.append(InvalidHunkNumbersError(self.line_number, f"Error checking numbers in: {stripped_line}"))

                return Token(token_type, stripped_line, self.line_number, errors)

        stripped_line = line.rstrip('\r\n')
        if stripped_line.strip():
            return Token(
                TokenType.ERROR, stripped_line, self.line_number,
                [UnrecognizedLineError(self.line_number, f"Line content: '{stripped_line}'")]
            )

        return None

# Parser class
class DiffParser:
    def __init__(self, tokens: List[Token], available_paths: Set[str] = None):
        self.original_tokens = tokens
        self.tokens = tokens
        self.current = 0
        self.available_paths = available_paths or set()
        self._errors: Set[ParseError] = set()

    @property
    def errors(self) -> List[ParseError]:
        all_errors = set(self._errors)
        for token in self.tokens:
            all_errors.update(token.errors)
        return sorted(list(all_errors), key=lambda e: e.line_number)

    def parse(self) -> List[DiffFile]:
        self.current = 0
        self._errors = set()
        diff_files = []

        if not self.tokens:
            return diff_files

        while self.current < len(self.tokens):
            start_token_index = self.current
            diff_file = self._parse_file()
            if diff_file:
                diff_files.append(diff_file)
            elif self.current < len(self.tokens):
                if self.current == start_token_index:
                    token = self.tokens[self.current]
                    if not any(isinstance(e, MissingFileHeaderError) for e in token.errors):
                        error = MissingFileHeaderError(
                            token.line_number,
                            f"Expected '---' to start file diff, found: {token.type}"
                        )
                        self._errors.add(error)
                        token.errors.append(error)
                    self.current += 1

                found_next_file = False
                while self.current < len(self.tokens):
                    token = self.tokens[self.current]
                    if token.type == TokenType.FILE_HEADER and token.value.startswith("---"):
                        found_next_file = True
                        break
                    self.current += 1
                if not found_next_file:
                    break
            else:
                break

        return diff_files

    def fix_errors(self) -> List[Token]:
        """Apply fixes for all errors and return the modified token list."""
        max_passes = 20  # Set to 20 per request
        for pass_num in range(max_passes):
            list_modified_in_pass = False
            restart_scan = False

            errors_before_fix = self.errors
            if not errors_before_fix:
                break

            error_token_map: Dict[ParseError, List[Tuple[int, Token]]] = {}
            for i, token in enumerate(self.tokens):
                for error in token.errors:
                    if error not in error_token_map:
                        error_token_map[error] = []
                    error_token_map[error].append((i, token))

            sorted_errors = sorted(errors_before_fix, key=lambda e: e.line_number)
            applied_fixes_this_pass = set()

            for error in sorted_errors:
                if (error.__class__, error.line_number) in applied_fixes_this_pass:
                    continue

                token_contexts = error_token_map.get(error)
                if not token_contexts:
                    continue

                current_token_index = -1
                original_token_instance = token_contexts[0][1]
                for idx, t in enumerate(self.tokens):
                    if t is original_token_instance:
                        current_token_index = idx
                        break

                if current_token_index == -1:
                    continue

                token = self.tokens[current_token_index]
                if error not in token.errors:
                    continue

                context = {
                    'token': token,
                    'tokens': self.tokens,
                    'current': current_token_index,
                    'available_paths': self.available_paths,
                    'list_modified': False
                }

                fixed_context = None
                try:
                    fixed_context = error.fix(context)
                except Exception as e:
                    print(f"Warning: Exception during fix for {error} on line {token.line_number}: {e}")

                if fixed_context:
                    applied_fixes_this_pass.add((error.__class__, error.line_number))
                    if fixed_context.get('list_modified'):
                        self.tokens = fixed_context['tokens']
                        list_modified_in_pass = True
                        restart_scan = True
                        break

            if restart_scan:
                self.parse()
                continue

            self.parse()
            errors_after_fix = self.errors

            if set(errors_after_fix) == set(errors_before_fix) and not list_modified_in_pass:
                break
            if not errors_after_fix:
                break

        self.parse()
        return self.tokens

    def fix_and_output(self) -> str:
        """
        Fix errors in the parsed diff (up to 20 passes) and output the fixed diff as a string.

        Returns:
            A string representing the fixed diff in unified diff format.
        """
        # Fix errors (up to 20 passes)
        self.fix_errors()

        # Get the fixed DiffFile list
        diff_files = self.parse()

        # Generate output by concatenating each DiffFile's string
        if not diff_files:
            return ""

        output_lines = []
        for diff_file in diff_files:
            output_lines.append(diff_file.to_string().rstrip('\n'))

        return '\n'.join(output_lines) + '\n'

    def _parse_file(self) -> Optional[DiffFile]:
        start_index = self.current
        if not (self.current < len(self.tokens) and self._match(TokenType.FILE_HEADER) and self.tokens[self.current].value.startswith("---")):
            if self.current < len(self.tokens):
                token = self.tokens[self.current]
                error = MissingFileHeaderError(
                    token.line_number,
                    f"File diff must start with '---', found: {token.type}"
                )
                self._errors.add(error)
                if error not in token.errors: token.errors.append(error)
            return None

        old_header_token = self.tokens[self.current]
        old_path = self._validate_file_header(old_header_token)
        self.current += 1

        new_path = None
        new_header_token = None
        if self.current < len(self.tokens) and self._match(TokenType.FILE_HEADER) and self.tokens[self.current].value.startswith("+++"):
            new_header_token = self.tokens[self.current]
            new_path = self._validate_file_header(new_header_token)
            self.current += 1
        else:
            if old_path and old_path != 'a/unknown' and old_path.startswith("a/"):
                new_path = "b/" + old_path[len("a/"):]
            elif old_path:
                new_path = 'b/unknown'
            else:
                new_path = 'b/unknown'

        hunks = []
        has_hunk_header_token = False
        first_failing_hunk_index = -1

        while self.current < len(self.tokens):
            token = self.tokens[self.current]
            if token.type == TokenType.FILE_HEADER and token.value.startswith("---"):
                break
            if token.type == TokenType.HUNK_HEADER:
                has_hunk_header_token = True
                hunk_start_index = self.current
                hunk = self._parse_hunk()
                if hunk:
                    hunks.append(hunk)
                elif first_failing_hunk_index == -1:
                    first_failing_hunk_index = hunk_start_index
            elif token.type == TokenType.ERROR:
                for e in token.errors:
                    self._errors.add(e)
                self.current += 1
            elif token.type in (TokenType.LINE_ADDED, TokenType.LINE_REMOVED, TokenType.LINE_CONTEXT, TokenType.NO_NEWLINE):
                error = UnrecognizedLineError(token.line_number, f"Unexpected diff line outside hunk: {token.type}")
                self._errors.add(error)
                if error not in token.errors: token.errors.append(error)
                self.current += 1
            else:
                error = UnrecognizedLineError(token.line_number, f"Unexpected token before hunk or next file: {token.type}")
                self._errors.add(error)
                if error not in token.errors: token.errors.append(error)
                self.current += 1

        if not hunks:
            error_line = old_header_token.line_number
            details = "File has headers but no valid hunks were parsed"
            if has_hunk_header_token:
                details = "File has headers but all hunks failed parsing or were empty"
            else:
                non_hunk_content_exists = False
                check_start = start_index + 1
                if new_header_token: check_start += 1
                end_check = self.current
                for i in range(check_start, end_check):
                    if self.tokens[i].type not in [
                        TokenType.FILE_HEADER, TokenType.HUNK_HEADER,
                        TokenType.LINE_ADDED, TokenType.LINE_REMOVED, TokenType.LINE_CONTEXT,
                        TokenType.NO_NEWLINE, TokenType.ERROR
                    ]:
                        non_hunk_content_exists = True
                        break
                    if self.tokens[i].type == TokenType.ERROR:
                        non_hunk_content_exists = True
                        break
                if non_hunk_content_exists:
                    details = "File has headers but no valid hunks found before unexpected content"
                else:
                    details = "File has headers but no hunk headers (@@) were found"

            error = NoHunksError(error_line, details)
            self._errors.add(error)
            if error not in old_header_token.errors: old_header_token.errors.append(error)

        return DiffFile(old_path, new_path, hunks)

    def _validate_file_header(self, token: Token) -> Optional[str]:
        prefix = "---" if token.value.startswith("---") else "+++"

        path_part = token.value[len(prefix):].strip()
        if not path_part or path_part == '/dev/null':
            is_valid_empty_format = (token.value.strip() == prefix or token.value.strip() == f"{prefix} /dev/null")
            if not is_valid_empty_format:
                error = InvalidFileHeaderError(token.line_number, f"Invalid format near path: {token.value}")
                self._errors.add(error)
                if error not in token.errors: token.errors.append(error)
            error = EmptyFilePathError(token.line_number, f"{prefix} header has empty or null path")
            self._errors.add(error)
            if error not in token.errors: token.errors.append(error)
            return ('a/' if prefix == '---' else 'b/') + "unknown"
        else:
            expected_dir_prefix = 'a/' if prefix == '---' else 'b/'
            if not path_part.startswith(('a/', 'b/')):
                path_part = expected_dir_prefix + path_part
            return path_part

    def _parse_hunk(self) -> Optional[Hunk]:
        if not self._match(TokenType.HUNK_HEADER):
            return None

        hunk_header_token = self.tokens[self.current]
        line_number = hunk_header_token.line_number
        hunk_header_index = self.current
        self.current += 1

        for error in hunk_header_token.errors:
            self._errors.add(error)

        match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", hunk_header_token.value)
        if not match:
            if not any(isinstance(e, InvalidHunkHeaderError) for e in hunk_header_token.errors):
                error = InvalidHunkHeaderError(
                    line_number, f"Invalid format: {hunk_header_token.value}"
                )
                self._errors.add(error)
                hunk_header_token.errors.append(error)
            self._skip_to_next_hunk_or_file()
            return None

        try:
            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) is not None else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) is not None else 1

            is_valid = True
            if old_start < 0 or old_count < 0 or new_start < 0 or new_count < 0:
                is_valid = False
            if old_start == 0 and old_count != 0: is_valid = False
            if new_start == 0 and new_count != 0: is_valid = False
            if old_count > 0 and old_start == 0: is_valid = False
            if new_count > 0 and new_start == 0: is_valid = False

            if not is_valid:
                if not any(isinstance(e, InvalidHunkNumbersError) for e in hunk_header_token.errors):
                    error = InvalidHunkNumbersError(
                        line_number, f"Invalid hunk numbers (start={old_start},{new_start} count={old_count},{new_count}): {hunk_header_token.value}"
                    )
                    self._errors.add(error)
                    hunk_header_token.errors.append(error)
                self._skip_to_next_hunk_or_file()
                return None
        except ValueError:
            if not any(isinstance(e, InvalidHunkNumbersError) for e in hunk_header_token.errors):
                error = InvalidHunkNumbersError(line_number, f"Hunk header contains non-integer values: {hunk_header_token.value}")
                self._errors.add(error)
                hunk_header_token.errors.append(error)
            self._skip_to_next_hunk_or_file()
            return None

        lines: List[DiffLine] = []
        actual_old_count = 0
        actual_new_count = 0
        hunk_lines_start_index = self.current

        while self.current < len(self.tokens):
            line_token = self.tokens[self.current]
            if line_token.type in (TokenType.LINE_ADDED, TokenType.LINE_REMOVED, TokenType.LINE_CONTEXT):
                content = line_token.value[1:] if len(line_token.value) > 0 else ""
                lines.append(DiffLine(content, line_token.type, line_token.line_number))
                if line_token.type in (TokenType.LINE_REMOVED, TokenType.LINE_CONTEXT):
                    actual_old_count += 1
                if line_token.type in (TokenType.LINE_ADDED, TokenType.LINE_CONTEXT):
                    actual_new_count += 1
                self.current += 1
            elif line_token.type == TokenType.NO_NEWLINE:
                content = line_token.value.strip()
                lines.append(DiffLine(content, line_token.type, line_token.line_number))
                self.current += 1
            elif line_token.type == TokenType.ERROR:
                for e in line_token.errors:
                    self._errors.add(e)
                actual_old_count += 1
                actual_new_count += 1
                lines.append(DiffLine(line_token.value, TokenType.LINE_CONTEXT, line_token.line_number))
                self.current += 1
            else:
                break

        is_truly_empty = not lines
        is_zero_count_hunk = old_count == 0 and new_count == 0

        if is_truly_empty and not is_zero_count_hunk:
            error = EmptyHunkError(line_number, "Hunk header expects lines, but none were found")
            self._errors.add(error)
            if error not in hunk_header_token.errors: hunk_header_token.errors.append(error)
            return None

        counts_match = (actual_old_count == old_count and actual_new_count == new_count)
        if not counts_match:
            error = HunkLineCountMismatchError(
                line_number,
                f"Header expects {old_count} old, {new_count} new lines; Found {actual_old_count} old, {actual_new_count} new"
            )
            self._errors.add(error)
            if error not in hunk_header_token.errors: hunk_header_token.errors.append(error)

        hunk = Hunk(old_start, old_count, new_start, new_count, lines)
        return hunk

    def _skip_to_next_hunk_or_file(self):
        while self.current < len(self.tokens):
            token = self.tokens[self.current]
            if token.type == TokenType.HUNK_HEADER or \
               (token.type == TokenType.FILE_HEADER and token.value.startswith("---")):
                break
            self.current += 1

    def _match(self, expected_type: str) -> bool:
        return self.current < len(self.tokens) and self.tokens[self.current].type == expected_type

def run_parse_fix_parse(content: str, available_paths: Set[str]) -> List[DiffFile]:
    """
    Lexes, parses, and attempts to fix errors in diff content.

    Args:
        content: The raw diff content string.
        available_paths: A set of available file paths for context during error fixing.

    Returns:
        A list of parsed DiffFile objects, potentially after fixing errors.
    """
    lexer = DiffLexer(content)
    tokens = lexer.tokenize()
    parser = DiffParser(tokens, available_paths)
    tries = 20
    while tries > 0:
        diffs = parser.parse()
        if not parser.errors:
            break
        parser.fix_errors()  # This updates parser.tokens internally
        tries -= 1
    # Final parse after fixing attempts
    diffs = parser.parse()
    return diffs


def run_parse_fix_parse(content: str, available_paths: Set[str]) -> List[DiffFile]:
    """
    Lexes, parses, and attempts to fix errors in diff content.

    Args:
        content: The raw diff content string.
        available_paths: A set of available file paths for context during error fixing.

    Returns:
        A list of parsed DiffFile objects, potentially after fixing errors.
    """
    lexer = DiffLexer(content)
    tokens = lexer.tokenize()
    parser = DiffParser(tokens, available_paths)
    tries = 20
    while tries > 0:
        diffs = parser.parse()
        if not parser.errors:
            break
        parser.fix_errors()  # This updates parser.tokens internally
        tries -= 1
    # Final parse after fixing attempts
    diffs = parser.parse()
    return diffs
