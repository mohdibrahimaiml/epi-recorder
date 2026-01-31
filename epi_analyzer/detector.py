"""
EPI Agent Mistake Detector

AI-powered analysis of agent execution to identify bugs:
- Infinite loops (same tool called repeatedly with errors)
- Hallucinations (confident LLM output followed by tool failures)
- Inefficiency (excessive token usage, repeated work)
- Repetitive patterns (agent redoing same queries)
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher


class MistakeDetector:
    """
    AI-powered agent bug detection.
    Analyzes .epi files to find infinite loops, hallucinations, inefficiencies.
    """
    
    def __init__(self, epi_file: str):
        """
        Initialize detector with an EPI recording file.
        
        Args:
            epi_file: Path to .epi file (can be .epi.db or steps.jsonl)
        """
        self.epi_path = Path(epi_file)
        self.steps = self._load_steps()
        self.mistakes: List[Dict] = []
    
    def _load_steps(self) -> List[Dict]:
        """Load steps from EPI file (ZIP, SQLite, or JSONL)"""
        import tempfile
        import zipfile
        
        # If it's a ZIP file (.epi), unpack it first
        if self.epi_path.is_file() and self.epi_path.suffix == '.epi':
            try:
                # Check if it's a valid ZIP
                if zipfile.is_zipfile(self.epi_path):
                    temp_dir = Path(tempfile.mkdtemp())
                    with zipfile.ZipFile(self.epi_path, 'r') as zf:
                        zf.extractall(temp_dir)
                    
                    # Look for steps.jsonl in extracted content
                    steps_file = temp_dir / "steps.jsonl"
                    if steps_file.exists():
                        return self._load_from_jsonl(steps_file)
                    
                    # Also check for SQLite db
                    for db_file in temp_dir.glob("*.db"):
                        try:
                            return self._load_from_sqlite(db_file)
                        except Exception:
                            continue
            except Exception:
                pass  # Fall through to other methods
        
        # Try loading from steps.jsonl in directory
        if self.epi_path.is_dir():
            jsonl_path = self.epi_path / "steps.jsonl"
            if jsonl_path.exists():
                return self._load_from_jsonl(jsonl_path)
            
            # Check for temp databases
            temp_dbs = list(self.epi_path.glob("*_temp.db"))
            if temp_dbs:
                return self._load_from_sqlite(temp_dbs[0])
        
        # Try as JSONL file directly
        if self.epi_path.suffix == '.jsonl':
            return self._load_from_jsonl(self.epi_path)
        
        # Try as SQLite database
        db_paths = [
            self.epi_path,
            self.epi_path.with_suffix('.epi.db'),
            self.epi_path / 'recording.db'
        ]
        
        for db_path in db_paths:
            if db_path.exists():
                try:
                    return self._load_from_sqlite(db_path)
                except Exception:
                    continue
        
        raise FileNotFoundError(f"No valid .epi file found at {self.epi_path}")
    
    def _load_from_jsonl(self, path: Path) -> List[Dict]:
        """Load steps from JSONL file"""
        steps = []
        with open(path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if line.strip():
                    step = json.loads(line)
                    steps.append({
                        'id': i,
                        'index': step.get('index', i),
                        'type': step.get('kind', 'unknown'),
                        'content': step.get('content', {}),
                        'timestamp': step.get('timestamp', '')
                    })
        return steps
    
    def _load_from_sqlite(self, db_path: Path) -> List[Dict]:
        """Load steps from SQLite database"""
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute('SELECT * FROM steps ORDER BY id')
        
        steps = []
        for row in cursor.fetchall():
            content = json.loads(row[3]) if isinstance(row[3], str) else row[3]
            steps.append({
                'id': row[0],
                'index': row[1],
                'type': row[2],
                'content': content,
                'timestamp': row[4] if len(row) > 4 else None
            })
        
        conn.close()
        return steps
    
    def analyze(self) -> List[Dict]:
        """Run all detection patterns"""
        self._detect_infinite_loops()
        self._detect_hallucinations()
        self._detect_inefficiency()
        self._detect_repetitive_patterns()
        return self.mistakes
    
    def _detect_infinite_loops(self):
        """Detect agent stuck calling same tool repeatedly"""
        # Look for LLM request/response patterns
        llm_steps = [s for s in self.steps if 'llm' in s['type'].lower()]
        
        if len(llm_steps) < 5:
            return
        
        # Check last N calls for repetition
        window = 5
        recent = llm_steps[-window:]
        
        # Extract patterns (model, messages similarity)
        patterns = []
        for step in recent:
            content = step.get('content', {})
            # Check if this is a request with messages
            messages = content.get('messages', [])
            if messages:
                # Get last user message
                user_msgs = [m for m in messages if m.get('role') == 'user']
                if user_msgs:
                    patterns.append(user_msgs[-1].get('content', '')[:100])
        
        # If we see very similar patterns repeated, it's likely a loop
        if len(patterns) >= 3:
            similarities = [
                self._calculate_similarity(patterns[i], patterns[i+1])
                for i in range(len(patterns)-1)
            ]
            avg_similarity = sum(similarities) / len(similarities)
            
            if avg_similarity > 0.8:  # 80% similar
                self.mistakes.append({
                    'type': 'INFINITE_LOOP',
                    'severity': 'CRITICAL',
                    'step': recent[-1]['id'],
                    'explanation': f'Agent appears stuck in a loop - repeated similar requests {window} times',
                    'fix': 'Add max_iterations limit or better error handling',
                    'cost_impact': 'High - stuck in loop burning API credits',
                    'pattern_similarity': f'{avg_similarity:.0%}'
                })
    
    def _detect_hallucinations(self):
        """Detect high-confidence LLM calls followed by errors"""
        for i, step in enumerate(self.steps[:-1]):
            if 'llm.response' not in step['type'].lower():
                continue
            
            content = step.get('content', {})
            
            # Check if next few steps show errors
            next_steps = self.steps[i+1:min(i+4, len(self.steps))]
            errors = [s for s in next_steps if 'error' in s['type'].lower()]
            
            if errors and content.get('provider') in ['openai', 'google']:
                # LLM gave response but then errors occurred
                choices = content.get('choices', [])
                if choices:
                    finish_reason = choices[0].get('finish_reason', 'stop')
                    if finish_reason == 'stop':  # Completed confidently
                        response_text = choices[0].get('message', {}).get('content', '')[:150]
                        
                        self.mistakes.append({
                            'type': 'HALLUCINATION',
                            'severity': 'HIGH',
                            'step': step['id'],
                            'explanation': 'LLM generated confident output but subsequent operations failed',
                            'details': f"LLM said: {response_text}...",
                            'error_step': errors[0]['id'],
                            'fix': 'Add output validation or use function calling with strict schemas'
                        })
    
    def _detect_inefficiency(self):
        """Detect expensive operations for simple tasks"""
        llm_responses = [s for s in self.steps if 'llm.response' in s['type'].lower()]
        
        if not llm_responses:
            return
        
        # Calculate token usage
        total_tokens = 0
        for step in llm_responses:
            content = step.get('content', {})
            usage = content.get('usage', {})
            if usage:
                total_tokens += usage.get('total_tokens', 0)
        
        step_count = len(self.steps)
        
        # Red flags
        flags = []
        
        if total_tokens > 10000 and step_count < 5:
            flags.append(f"High token usage ({total_tokens:,} tokens) for simple workflow")
        
        # Estimate cost (rough)
        # GPT-4: ~$0.03/1K input, ~$0.06/1K output - use avg $0.045/1K
        estimated_cost = (total_tokens / 1000) * 0.045
        if estimated_cost > 0.50:
            flags.append(f"Expensive execution (~${estimated_cost:.2f})")
        
        # Check for model inefficiency (using GPT-4 when GPT-3.5 would work)
        gpt4_calls = sum(1 for s in llm_responses 
                        if 'gpt-4' in s.get('content', {}).get('model', '').lower())
        if gpt4_calls > 0 and step_count < 3:
            flags.append(f"Using GPT-4 for simple task ({gpt4_calls} calls)")
        
        if flags:
            self.mistakes.append({
                'type': 'INEFFICIENT',
                'severity': 'MEDIUM',
                'step': llm_responses[-1]['id'],
                'explanation': '; '.join(flags),
                'metrics': {
                    'total_tokens': total_tokens,
                    'estimated_cost': round(estimated_cost, 2),
                    'step_count': step_count,
                    'llm_calls': len(llm_responses)
                },
                'fix': 'Consider using GPT-3.5-turbo or caching responses'
            })
    
    def _detect_repetitive_patterns(self):
        """Detect agent redoing same work"""
        if len(self.steps) < 10:
            return
        
        # Look for repeated LLM requests
        llm_requests = [s for s in self.steps if 'llm.request' in s['type'].lower()]
        
        if len(llm_requests) < 3:
            return
        
        # Extract user messages
        queries = []
        for step in llm_requests:
            content = step.get('content', {})
            messages = content.get('messages', [])
            for msg in messages:
                if msg.get('role') == 'user':
                    queries.append((step['id'], msg.get('content', '')[:100]))
                    break
        
        # Find similar queries
        for i in range(len(queries)):
            for j in range(i+1, len(queries)):
                similarity = self._calculate_similarity(queries[i][1], queries[j][1])
                if similarity > 0.7:  # 70% similar
                    self.mistakes.append({
                        'type': 'REPETITIVE_PATTERN',
                        'severity': 'LOW',
                        'step': queries[j][0],
                        'explanation': f'Similar query repeated (steps {queries[i][0]} and {queries[j][0]})',
                        'pattern': f'"{queries[i][1][:50]}..."',
                        'fix': 'Implement memory/caching to avoid redundant LLM calls'
                    })
                    return  # Only report first instance
    
    def _calculate_similarity(self, a: str, b: str) -> float:
        """Simple string similarity using SequenceMatcher"""
        return SequenceMatcher(None, a, b).ratio()
    
    def get_summary(self) -> str:
        """Human-readable summary of detected mistakes"""
        if not self.mistakes:
            return "[OK] No obvious mistakes detected"
        
        # Count by severity
        critical = sum(1 for m in self.mistakes if m.get('severity') == 'CRITICAL')
        high = sum(1 for m in self.mistakes if m.get('severity') == 'HIGH')
        medium = sum(1 for m in self.mistakes if m.get('severity') == 'MEDIUM')
        low = sum(1 for m in self.mistakes if m.get('severity') == 'LOW')
        
        lines = [
            f"[!] Found {len(self.mistakes)} issue(s):",
            f"   {critical} Critical, {high} High, {medium} Medium, {low} Low severity",
            ""
        ]
        
        # Show details for each mistake
        for i, m in enumerate(self.mistakes, 1):
            severity_marker = {
                'CRITICAL': '[!!!]',
                'HIGH': '[!!]',
                'MEDIUM': '[!]',
                'LOW': '[-]'
            }.get(m.get('severity', 'LOW'), '[?]')
            
            lines.append(f"{i}. {severity_marker} [{m.get('severity')}] {m.get('type')} at Step {m.get('step')}")
            lines.append(f"   -> {m.get('explanation')}")
            if 'fix' in m:
                lines.append(f"   -> Fix: {m['fix']}")
            lines.append("")
        
        return '\n'.join(lines)
        
        return '\n'.join(lines)

