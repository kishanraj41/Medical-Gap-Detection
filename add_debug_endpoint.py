with open('mcp_server.py', 'r') as f:
    content = f.read()

# Add debug endpoint before the "if __name__" section
debug_endpoint = '''

@app.get("/debug/patient/{patient_id}")
async def debug_patient(patient_id: str, request: Request):
    """Debug endpoint to see raw patient data"""
    from fhir_adapter import FHIRClient, FHIRPatientExtractor
    
    ctx = get_sharp_context(request)
    fhir_url = ctx.get("fhir_server_url", "")
    
    if not fhir_url:
        return {"error": "No FHIR server URL in context", "patient_id": patient_id}
    
    client = FHIRClient(fhir_url, ctx.get("access_token", ""))
    extractor = FHIRPatientExtractor(client)
    
    try:
        demographics = extractor.get_patient_demographics(patient_id)
        profile = extractor.extract_patient(patient_id)
        
        return {
            "patient_id": patient_id,
            "fhir_server": fhir_url,
            "demographics": demographics,
            "data_counts": {
                "notes": len(profile.get("clinical_notes", [])),
                "labs": len(profile.get("observations", [])),
                "meds": len(profile.get("medications", [])),
                "conditions": len(profile.get("conditions", [])),
            }
        }
    except Exception as e:
        return {"error": str(e), "patient_id": patient_id, "fhir_server": fhir_url}
'''

# Insert before "if __name__"
if_main_pos = content.find('if __name__ == "__main__":')
if if_main_pos > 0:
    content = content[:if_main_pos] + debug_endpoint + '\n' + content[if_main_pos:]
    
    with open('mcp_server.py', 'w') as f:
        f.write(content)
    print("✅ Added debug endpoint")
else:
    print("❌ Could not find if __name__ block")
