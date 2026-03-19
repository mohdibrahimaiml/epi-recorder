"""
SQLite-based storage for EPI recordings.

Provides atomic, crash-safe storage replacing JSONL files.
SQLite transactions ensure no data corruption on crashes.
"""

import sqlite3
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from .schemas import StepModel
from .time_utils import utc_now_iso
from .workspace import RecordingWorkspaceError, ensure_workspace_writable


class EpiStorage:
    """
    SQLite-based atomic storage for agent execution.
    Replaces JSONL (which corrupts on crashes).
    """
    
    def __init__(self, session_id: str, output_dir: Path):
        """
        Initialize SQLite storage.
        
        Args:
            session_id: Unique session identifier
            output_dir: Directory for database file
        """
        self.session_id = session_id
        self.output_dir = Path(output_dir)
        ensure_workspace_writable(self.output_dir)
        
        self.db_path = self.output_dir / f"{session_id}_temp.db"
        try:
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        except sqlite3.OperationalError as exc:
            raise RecordingWorkspaceError(
                f"EPI could not open its recording database at '{self.db_path}'. "
                "The recording workspace is unavailable or not writable. "
                "Try setting TMP/TEMP to a writable folder and rerun."
            ) from exc
        self._init_tables()
    
    def _init_tables(self):
        """Initialize database schema"""
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                step_index INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        ''')
        
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        
        self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_steps_index 
            ON steps(step_index)
        ''')
        
        self.conn.commit()
    
    def add_step(self, step: StepModel) -> None:
        """
        Atomic insert of execution step.
        Survives process crashes.
        
        Args:
            step: StepModel to persist
        """
        self.conn.execute(
            '''INSERT INTO steps 
               (step_index, timestamp, kind, content, created_at) 
               VALUES (?, ?, ?, ?, ?)''',
            (
                step.index,
                step.timestamp.isoformat(),
                step.kind,
                step.model_dump_json(),
                time.time()
            )
        )
        self.conn.commit()
    
    def get_steps(self) -> List[StepModel]:
        """
        Retrieve all steps in order.
        
        Returns:
            List of StepModel instances
        """
        cursor = self.conn.execute(
            'SELECT content FROM steps ORDER BY step_index'
        )
        rows = cursor.fetchall()
        
        steps = []
        for row in rows:
            step_data = json.loads(row[0])
            steps.append(StepModel(**step_data))
        
        return steps
    
    def set_metadata(self, key: str, value: str) -> None:
        """
        Set metadata key-value pair.
        
        Args:
            key: Metadata key
            value: Metadata value
        """
        self.conn.execute(
            'INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)',
            (key, value)
        )
        self.conn.commit()
    
    def get_metadata(self, key: str) -> Optional[str]:
        """
        Get metadata value.
        
        Args:
            key: Metadata key
            
        Returns:
            Metadata value or None
        """
        cursor = self.conn.execute(
            'SELECT value FROM metadata WHERE key = ?',
            (key,)
        )
        row = cursor.fetchone()
        return row[0] if row else None
    
    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
    
    def export_to_jsonl(self, output_path: Path) -> None:
        """
        Export steps to JSONL file for backwards compatibility.
        
        Args:
            output_path: Path to JSONL file
        """
        steps = self.get_steps()
        with open(output_path, 'w', encoding='utf-8') as f:
            for step in steps:
                f.write(step.model_dump_json() + '\n')
    
    def finalize(self) -> Path:
        """
        Finalize recording: export steps to JSONL, close DB, clean up temp file.

        Returns:
            Path to finalized JSONL file
        """
        # Add finalization metadata before exporting
        self.set_metadata('finalized_at', utc_now_iso())
        self.set_metadata('session_id', self.session_id)

        # Export to JSONL while connection is still open
        final_path = self.output_dir / "steps.jsonl"
        self.export_to_jsonl(final_path)

        # Now close and clean up the temp DB
        self.close()
        self.db_path.unlink(missing_ok=True)

        return final_path



 
