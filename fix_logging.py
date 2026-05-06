import re

with open('mcp_server.py', 'r') as f:
    content = f.read()

# Find the logging.basicConfig line and replace it
old_logging = '''logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")'''

new_logging = '''# Cloud Run compatible logging - outputs to stdout
import sys
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
    force=True  # Override any existing config
)'''

content = content.replace(old_logging, new_logging)

with open('mcp_server.py', 'w') as f:
    f.write(content)

print("✅ Fixed logging configuration for Cloud Run")
