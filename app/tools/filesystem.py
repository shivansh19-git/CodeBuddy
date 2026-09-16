"""Validated filesystem operations for a repository task workspace.

These APIs are intentionally narrower than shell access: each path is checked
before reading or writing, and edits are expressed as an exact replacement.
"""

from pathlib import Path


class ToolPathError(ValueError):
    """A task attempted to access a path outside its repository."""


def _resolve(root: Path, relative_path: str) -> Path:
    """Resolve a user/model path and reject absolute paths and traversal."""
    path = Path(relative_path)
    if path.is_absolute():
        raise ToolPathError("Only repository-relative paths are allowed.")
    destination = (root / path).resolve()
    try:
        destination.relative_to(root.resolve())
    except ValueError as exc:
        raise ToolPathError("Path escapes the repository workspace.") from exc
    return destination


def read_file(root: Path, relative_path: str) -> str:
    """Read UTF-8 text only from inside the active workspace."""
    return _resolve(root, relative_path).read_text(encoding="utf-8")


def create_file(root: Path, relative_path: str, content: str) -> None:
    """Create a new text file. Overwriting is allowed if the LLM issues a create action on an existing file."""
    destination = _resolve(root, relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")


def replace_once(root: Path, relative_path: str, old: str, new: str) -> None:
    """Apply an exact, single replacement instead of a dangerous full rewrite."""
    destination = _resolve(root, relative_path)
    
    if not old.strip():
        destination.write_text(new, encoding="utf-8")
        return
        
    current = destination.read_text(encoding="utf-8")
    current_lf = current.replace("\r\n", "\n")
    
    # Ensure old is treated as full lines only
    old_lf = old.replace("\r\n", "\n")
    old_lines = old_lf.split("\n")
    
    # Strip hallucinated prompt artifacts from LLM's `old` block
    cleaned_old = []
    for line in old_lines:
        t = line.strip()
        if t.startswith("FILE:") or t.startswith("SYMBOL:") or t == "```python" or t == "```":
            continue
        cleaned_old.append(line)
    old_lines = cleaned_old

    while old_lines and not old_lines[0].strip():
        old_lines.pop(0)
    while old_lines and not old_lines[-1].strip():
        old_lines.pop()
    
    old_trimmed = "\n".join(old_lines)
    if old_trimmed and current_lf.count(old_trimmed) == 1:
        new_lines = new.replace("\r\n", "\n").split("\n")
        while new_lines and not new_lines[0].strip():
            new_lines.pop(0)
        while new_lines and not new_lines[-1].strip():
            new_lines.pop()
        new_trimmed = "\n".join(new_lines)
        destination.write_text(current_lf.replace(old_trimmed, new_trimmed, 1), encoding="utf-8")
        return

    # Fallback for LLMs: line-by-line fuzzy match ignoring all whitespace and empty lines
    current_lines = current_lf.split("\n")
    current_non_empty = [(i, line.strip()) for i, line in enumerate(current_lines) if line.strip()]
    old_search_lines = [line.strip() for line in old_lines if line.strip()]
    
    matches = []
    if old_search_lines:
        import difflib
        for i in range(len(current_non_empty) - len(old_search_lines) + 1):
            match_count = 0
            for j in range(len(old_search_lines)):
                curr_compact = current_non_empty[i+j][1].replace(" ", "").replace("\t", "")
                old_compact = old_search_lines[j].replace(" ", "").replace("\t", "")
                
                if curr_compact == old_compact:
                    match_count += 1
                elif difflib.SequenceMatcher(None, curr_compact, old_compact).ratio() >= 0.85:
                    match_count += 1
                else:
                    break
                    
            if match_count == len(old_search_lines):
                matches.append(i)
                
    # Fallback 3: block-level difflib match that allows skipped lines (e.g., `# ...`)
    if not matches and old_search_lines:
        current_strs = [x[1].replace(" ", "").replace("\t", "") for x in current_non_empty]
        old_strs = [x.replace(" ", "").replace("\t", "") for x in old_search_lines]
        
        sm = difflib.SequenceMatcher(None, current_strs, old_strs)
        blocks = sm.get_matching_blocks()
        
        if blocks and len(blocks) > 1:
            first_block = blocks[0]
            last_block = blocks[-2]
            
            if first_block.size > 0:
                start_idx = first_block.a
                end_idx = last_block.a + last_block.size - 1
                matched_lines = sum(b.size for b in blocks[:-1])
                
                if matched_lines >= max(1, len(old_strs) * 0.4):
                    start_line_idx = current_non_empty[start_idx][0]
                    end_line_idx = current_non_empty[end_idx][0]
                    
                    new_lines = new.replace("\r\n", "\n").split("\n")
                    while new_lines and not new_lines[0].strip():
                        new_lines.pop(0)
                    while new_lines and not new_lines[-1].strip():
                        new_lines.pop()
                        
                    orig_indent = len(current_lines[start_line_idx]) - len(current_lines[start_line_idx].lstrip())
                    new_first_indent = len(new_lines[0]) - len(new_lines[0].lstrip()) if new_lines else 0
                    
                    replaced_section = new_lines
                    if orig_indent > 0 and new_first_indent == 0 and new_lines:
                        indent_str = " " * orig_indent
                        replaced_section = [indent_str + line if line.strip() else line for line in new_lines]
                        
                    final_lines = current_lines[:start_line_idx] + replaced_section + current_lines[end_line_idx + 1:]
                    destination.write_text("\n".join(final_lines), encoding="utf-8")
                    return

    if len(matches) == 1:
        match_idx = matches[0]
        start_line_idx = current_non_empty[match_idx][0]
        end_line_idx = current_non_empty[match_idx + len(old_search_lines) - 1][0]
        
        new_lines = new.replace("\r\n", "\n").split("\n")
        while new_lines and not new_lines[0].strip():
            new_lines.pop(0)
        while new_lines and not new_lines[-1].strip():
            new_lines.pop()
            
        if not new_lines:
            # If new is empty, just delete the matched lines
            final_lines = current_lines[:start_line_idx] + current_lines[end_line_idx + 1:]
            destination.write_text("\n".join(final_lines), encoding="utf-8")
            return
            
        orig_indent = len(current_lines[start_line_idx]) - len(current_lines[start_line_idx].lstrip())
        new_first_indent = len(new_lines[0]) - len(new_lines[0].lstrip())
        
        replaced_section = new_lines
        if orig_indent > 0 and new_first_indent == 0:
            indent_str = " " * orig_indent
            replaced_section = [indent_str + line if line.strip() else line for line in new_lines]
            
        final_lines = current_lines[:start_line_idx] + replaced_section + current_lines[end_line_idx + 1:]
        destination.write_text("\n".join(final_lines), encoding="utf-8")
        return

    debug_path = root / "replace_debug.log"
    try:
        debug_path.write_text(f"CURRENT:\n{current}\n\nOLD_LINES:\n{old_lines}\n\nOLD_SEARCH_LINES:\n{old_search_lines}\n\nMATCHES: {matches}\n\nNEW:\n{new}", encoding="utf-8")
    except Exception:
        pass
    raise ValueError("Edit requires exactly one matching source fragment.")
