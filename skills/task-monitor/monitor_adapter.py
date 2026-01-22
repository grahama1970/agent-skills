"""
monitor_adapter.py - Python adapter for Task Monitor.

Provides a tqdm-like wrapper that updates task-monitor state.
Supports both local file-write (default) and API push (for distributed).

Usage:
    from monitor_adapter import Monitor

    # Local file mode (default)
    # Writes to .batch_state.json in current directory
    for item in Monitor(items, name="my-task", total=1000):
        process(item)

    # Remote/API mode
    # Pushes updates to the task-monitor API
    for item in Monitor(items, name="my-task", api_url="http://localhost:8765"):
        process(item)
"""
import json
import os
import time
from pathlib import Path
from typing import Iterable, Optional, Any

try:
    import requests
except ImportError:
    requests = None

class Monitor:
    """tqdm-like progress monitor that updates Task Monitor state."""
    
    def __init__(
        self,
        iterable: Optional[Iterable] = None,
        name: str = "task",
        total: Optional[int] = None,
        desc: str = "",
        state_file: Optional[str] = None,
        api_url: Optional[str] = None,
        update_interval: int = 1, # Update freq (items)
        min_interval_s: float = 1.0, # Min time between updates to reduce I/O
    ):
        self.iterable = iterable
        self.name = name
        self.desc = desc
        self.total = total or (len(iterable) if hasattr(iterable, "__len__") else None)
        self.api_url = api_url
        
        # Throttling
        self.update_interval = update_interval
        self.min_interval_s = min_interval_s
        self.last_update_time = 0.0
        
        # State
        self.completed = 0
        self.failed = 0
        self.start_time = time.time()
        self.current_item = ""
        
        # Determine state file path
        if state_file:
            self.state_file = Path(state_file).resolve()
        else:
            # Default to local .batch_state.json in current dir
            self.state_file = Path.cwd() / ".batch_state.json"

    def __iter__(self):
        if self.iterable is None:
            return
            
        self._update() # Initial
        
        for item in self.iterable:
            self.current_item = str(item)[:50]
            yield item
            self.completed += 1
            
            # Throttle updates
            now = time.time()
            if (self.completed % self.update_interval == 0 and 
                now - self.last_update_time >= self.min_interval_s):
                self._update()
                
        self._update(final=True)

    def update(self, n=1, item=None):
        """Manual update for non-iterable use."""
        self.completed += n
        if item:
            self.current_item = str(item)[:50]
            
        now = time.time()
        if (self.completed % self.update_interval == 0 and 
            now - self.last_update_time >= self.min_interval_s):
            self._update()

    def set_description(self, desc):
        self.desc = desc
        
    def fail(self):
        """Register a failure."""
        self.failed += 1
        
    def _update(self, final=False):
        state = {
            "completed": self.completed,
            "total": self.total,
            "description": self.desc,
            "current_item": self.current_item,
            "stats": {
                "success": self.completed - self.failed,
                "failed": self.failed
            },
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "completed" if final else "running"
        }
        
        self.last_update_time = time.time()
        
        if self.api_url:
            if requests:
                try:
                    # Push to API
                    url = f"{self.api_url}/tasks/{self.name}/state"
                    requests.post(url, json=state, timeout=0.5)
                except Exception:
                    pass # Silent fail
        else:
            # Write to file
            try:
                with open(self.state_file, 'w') as f:
                    json.dump(state, f)
            except Exception:
                pass
