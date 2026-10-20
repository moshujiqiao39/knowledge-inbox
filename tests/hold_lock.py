import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from inbox.instance import SingleInstance

holder = SingleInstance(Path(sys.argv[1]))
print("LOCKED", flush=True)
time.sleep(30)
holder.close()
