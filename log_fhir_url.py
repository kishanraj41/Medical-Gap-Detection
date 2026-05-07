with open('mcp_server.py', 'r') as f:
    content = f.read()

# Find the tool_detect_gaps function and add logging RIGHT after getting context
old_code = '''async def call_tool(tool_name: str, arguments: dict, ctx: dict) -> Any:
    """Route tool calls to implementations."""
    validate_sharp_context(ctx)

    from fhir_adapter import FHIRClient, FHIRPatientExtractor
    client = FHIRClient(ctx["fhir_server_url"], ctx.get("access_token", ""))
    extractor = FHIRPatientExtractor(client)'''

new_code = '''async def call_tool(tool_name: str, arguments: dict, ctx: dict) -> Any:
    """Route tool calls to implementations."""
    validate_sharp_context(ctx)
    
    # LOG THE ACTUAL FHIR URL FROM PROMPT OPINION
    log.info(f"🔍 FHIR Server URL from Prompt Opinion: {ctx.get('fhir_server_url')}")
    log.info(f"🔍 Access Token present: {bool(ctx.get('access_token'))}")
    log.info(f"🔍 Patient ID from context: {ctx.get('patient_id')}")

    from fhir_adapter import FHIRClient, FHIRPatientExtractor
    client = FHIRClient(ctx["fhir_server_url"], ctx.get("access_token", ""))
    extractor = FHIRPatientExtractor(client)'''

content = content.replace(old_code, new_code)

with open('mcp_server.py', 'w') as f:
    f.write(content)
print("✅ Added FHIR URL logging")
