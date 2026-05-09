import sys
import os
sys.path.append(r"c:\Projects\Operator\backend")
from memory import append_to_daily_note

# Test appending a log
success_log = append_to_daily_note("This is a test note from the newly implemented system.", section="Log")
print(f"Log appended: {success_log}")

# Test appending a task
success_task = append_to_daily_note("- [ ] Test task #priority-high", section="Tasks", tags=["task"])
print(f"Task appended: {success_task}")
