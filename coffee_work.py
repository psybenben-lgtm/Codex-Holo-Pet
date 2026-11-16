"""Read the main Codex session's work phase from local lifecycle events."""

import json
from pathlib import Path
import time


WORK_EVENTS = {'task_started': 'working', 'task_complete': 'idle', 'turn_aborted': 'idle'}


def has_codex_cli():
    """无侵入检测本机是否存在 Codex CLI 会话目录（空白电脑不存在时自动返回 False）。"""
    try:
        sessions = Path.home() / '.codex' / 'sessions'
        return sessions.is_dir() and any(sessions.glob('*/*/*/*.jsonl'))
    except OSError:
        return False


def belongs_to_workspace(path, workspace):
    try:
        with path.open('rb') as handle:
            entry = json.loads(handle.readline())
    except (OSError, ValueError):
        return None
    meta = entry.get('payload', {})
    source = meta.get('source')
    if isinstance(source, dict) and 'subagent' in source:
        return False
    cwd = meta.get('cwd')
    return isinstance(cwd, str) and Path(cwd.removeprefix('\\\\?\\')).resolve() == workspace


def work_states(workspace, thread_id=None):
    """Yield phase changes without exposing the content of the session."""
    sessions = Path.home() / '.codex' / 'sessions'
    matches = {}
    current_path = signature = previous = None
    offset = 0
    phase = 'waiting'

    while True:
        try:
            candidates = []
            for path in sessions.glob('*/*/*/*.jsonl'):
                if not thread_id or path.stem.endswith(thread_id):
                    try:
                        stat = path.stat()
                    except FileNotFoundError:
                        continue
                    candidates.append((stat.st_mtime_ns, stat.st_size, path))

            for modified, size, path in sorted(candidates, reverse=True):
                if path not in matches:
                    match = belongs_to_workspace(path, workspace)
                    if match is not None:
                        matches[path] = match
                if not matches.get(path):
                    continue
                if (modified, size, path) != signature:
                    if path != current_path or size < offset:
                        phase, offset = 'waiting', 0
                    with path.open('rb') as handle:
                        handle.seek(offset)
                        for line in handle:
                            if not line.endswith(b'\n'):
                                break
                            offset += len(line)
                            try:
                                event = json.loads(line)
                            except ValueError:
                                continue
                            if event.get('type') == 'event_msg':
                                phase = WORK_EVENTS.get(event.get('payload', {}).get('type'), phase)
                    current_path, signature = path, (modified, size, path)
                break
            else:
                current_path = signature = None
                phase, offset = 'waiting', 0
        except OSError:
            pass

        if phase != previous:
            previous = phase
            yield phase
        time.sleep(.8)
