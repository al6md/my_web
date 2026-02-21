
import os

log_file = r'logs/recommendations.log'

if os.path.exists(log_file):
    try:
        with open(log_file, 'rb') as f:
            # Seek to end
            f.seek(0, 2)
            size = f.tell()
            # Read last 10KB
            f.seek(max(size - 10000, 0))
            lines = f.readlines()
            # Decode last lines
            print("--- Last Log Lines ---")
            for line in lines[-20:]:
                try:
                    print(line.decode('utf-8', errors='ignore').strip())
                except:
                    pass
    except Exception as e:
        print(f"Error reading log: {e}")
else:
    print("Log file not found.")
