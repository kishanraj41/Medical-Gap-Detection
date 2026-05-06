import re

# Read the file
with open('mcp_server.py', 'r') as f:
    content = f.read()

# Fix 1: Make patient_id optional in detect_coding_gaps tool
old_schema = '''        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "FHIR Patient ID to analyze",
                },
            },
            "required": ["patient_id"],
        },'''

new_schema = '''        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "FHIR Patient ID to analyze (optional if patient context is set via SHARP headers)",
                },
            },
            "required": [],
        },'''

content = content.replace(old_schema, new_schema)

# Fix 2: Update tool_detect_gaps to use context when patient_id not provided
old_function = '''async def tool_detect_gaps(extractor, arguments: dict, ctx: dict) -> dict:
    """Run the full gap detection pipeline on a patient."""
    patient_id = arguments.get("patient_id") or ctx.get("patient_id", "")
    if not patient_id:
        return {"error": "patient_id required"}'''

new_function = '''async def tool_detect_gaps(extractor, arguments: dict, ctx: dict) -> dict:
    """Run the full gap detection pipeline on a patient."""
    # Use patient_id from arguments OR from SHARP context headers
    patient_id = arguments.get("patient_id") or ctx.get("patient_id", "")
    
    if not patient_id:
        return {
            "error": "No patient_id provided. Either pass patient_id in arguments or ensure X-Patient-ID header is set.",
            "context_available": bool(ctx.get("patient_id"))
        }'''

content = content.replace(old_function, new_function)

# Write the fixed file
with open('mcp_server.py', 'w') as f:
    f.write(content)

print("✅ Fixed patient context handling in mcp_server.py")
