"""Make sure the data folder exists and belongs to the app user, then drop root."""
import os
import sys

UID = GID = 1000
data = os.environ.get("DATA_DIR", "/data")

if os.getuid() == 0:
    os.makedirs(data, exist_ok=True)
    for root, dirs, files in os.walk(data):
        for name in [root] + [os.path.join(root, n) for n in dirs + files]:
            try:
                os.chown(name, UID, GID)
            except OSError as e:
                print(f"entrypoint: could not chown {name}: {e}", flush=True)
    os.setgroups([])
    os.setgid(GID)
    os.setuid(UID)
    os.environ["HOME"] = "/home/hq"

if not os.access(data, os.W_OK):
    print(f"entrypoint: {data} is not writable; the app will not be able to save anything", flush=True)

os.execvp(sys.argv[1], sys.argv[1:])
