import re

def extract_device_info(text: str):
    model = re.search(r"(ISR\d+|ASR\d+|C\d{4}|Nexus\s\d+)", text)
    version = re.search(r"Version\s([\d\.]+)", text)

    return {
        "model": model.group(0) if model else None,
        "version": version.group(1) if version else None
    }

def build_query_from_device(info):
    return f"{info['model']} end of life and licensing information"
