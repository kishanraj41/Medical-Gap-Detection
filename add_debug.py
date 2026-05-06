with open('mcp_server.py', 'r') as f:
    content = f.read()

# Find the function and add debug logging right after the docstring
old_code = '''async def tool_detect_gaps(extractor, arguments: dict, ctx: dict) -> dict:
    """Run the full gap detection pipeline on a patient."""
    # Use patient_id from arguments OR from SHARP context headers
    patient_id = arguments.get("patient_id") or ctx.get("patient_id", "")'''

new_code = '''async def tool_detect_gaps(extractor, arguments: dict, ctx: dict) -> dict:
    """Run the full gap detection pipeline on a patient."""
    # DEBUG LOGGING
    log.info(f"🔍 DEBUG - Context received: {ctx}")
    log.info(f"🔍 DEBUG - Arguments received: {arguments}")
    
    # Use patient_id from arguments OR from SHARP context headers
    patient_id = arguments.get("patient_id") or ctx.get("patient_id", "")
    log.info(f"🔍 DEBUG - Resolved patient_id: {patient_id}")'''

content = content.replace(old_code, new_code)

with open('mcp_server.py', 'w') as f:
    f.write(content)

print("✅ Added debug logging to mcp_server.py")
