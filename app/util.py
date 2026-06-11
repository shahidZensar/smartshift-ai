import re
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
import numpy as np
import pandas as pd
from typing import Tuple, Optional, Dict, Any
from . import logger

def clean_sql(sql: str) -> str:
    # remove ```sql and ``` markers
    return re.sub(r"```sql|```", "", sql, flags=re.IGNORECASE).strip()

def safe_text(text: str) -> str:
    # Basic sanitization to prevent injection or formatting issues
    return text.replace("{", "{{").replace("}", "}}").replace("%", "%%")

def format_sql_response(sql_response) -> tuple:
    try:
        query_section, params_section = sql_response.split("PARAMS:")
        query = query_section.replace("QUERY:", "").strip()
        #query = query.replace("\n", "").strip()
        #query = query.replace("\n", "").strip()
        query = re.sub(r'\s+', ' ', query)
        params = tuple(p.strip().strip('"').strip("'") for p in params_section.split(",") if p.strip())
        logger.info("Formatted SQL query: %r with params: %r", query, params)
        return query, params
    except Exception as e:
        logger.error(f"Error formatting SQL response: {str(e)}")
        return None, None
    
def json_serializer(obj):
    if isinstance(obj, (np.integer,)):
        logger.info(f"Serializing numpy integer: {obj}")
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if pd.isna(obj):
        return None
    return str(obj)


class PromptOptimizer:
    """Optimizes prompts for different model sizes (small, medium, large)."""
    
    MODEL_SIZE_PATTERNS = {
        'small': ['gemma', 'phi', 'tinyllama', 'orca-2-3b', '3b', '1b', '2b'],
        'medium': ['llama2-7b', 'mistral', 'neural-chat', '7b', '10b', '13b'],
        'large': ['gpt', 'claude', 'llama2-13b', 'llama2-70b', 'llama3', '30b', '70b']
    }
    
    @classmethod
    def detect_model_size(cls, model_name: str) -> str:
        """Detect model size category from model name."""
        model_lower = model_name.lower()
        
        for size, patterns in cls.MODEL_SIZE_PATTERNS.items():
            for pattern in patterns:
                if pattern in model_lower:
                    return size
        return 'medium'  # Default to medium
    
    @classmethod
    def get_final_prompt(cls, model_name: str = 'medium') -> ChatPromptTemplate:
        """Get optimized final_prompt based on model size."""
        size = cls.detect_model_size(model_name) if isinstance(model_name, str) else 'medium'
        
        if size == 'small':
            return cls._get_small_model_prompt()
        elif size == 'large':
            return cls._get_large_model_prompt()
        else:
            return cls._get_medium_model_prompt()
    
    @staticmethod
    def _get_small_model_prompt() -> ChatPromptTemplate:
        """Optimized for small models (< 7B params): Very direct, minimal instructions."""
        return ChatPromptTemplate.from_template("""You are a device support assistant.

DEVICE DATA: {sql_context}
GUIDANCE: {rag_context}
QUESTION: {question}
TODAY: {current_date}

For each device:
1. Get: product_description, location, pak/serial_number, instance_number, qty, last_date_of_support
2. Calculate days until EOL: (last_date_of_support - TODAY)
3. Risk: CRITICAL (≤30d), HIGH (31-90d), MEDIUM (91-180d), LOW (>180d), UNKNOWN (missing)
4. Suggest: replacement or upgrade

Output format (one line per device):
Device: <product_number>
Description: <product_description>
Location: <location>
PAK: <pak/serial_number>
Instance: <instance_number>
Qty: <qty>
Support Ends: <last_date_of_support>
Days to EOL: <days or N/A>
Risk: <CRITICAL|HIGH|MEDIUM|LOW|UNKNOWN>
Action: <replacement recommendation>
Summary: <one-line status>""")
    
    @staticmethod
    def _get_medium_model_prompt() -> ChatPromptTemplate:
        """Optimized for medium models (7B-13B): Balanced detail and clarity."""
        return ChatPromptTemplate.from_template("""You are an Enterprise Smart Network Device Migration support assistant.

TASK: Analyze device inventory for EOL migration planning.

INPUTS:
DEVICE DATA: {sql_context}
REPLACEMENT GUIDANCE: {rag_context}
USER QUESTION: {question}
CURRENT DATE: {current_date}

PROCESSING RULES:
1. If no devices found, output: "No devices found matching the criteria."
2. Parse each device record exactly as provided - extract:
   - product_description, location, pak/serial_number, instance_number, qty, last_date_of_support
3. For each device:
   - Calculate Days Until EOL: Use exact calendar day count (last_date_of_support - TODAY)
   - Assign Risk Level:
     * CRITICAL: EOL passed or ≤ 30 days
     * HIGH: 31-90 days
     * MEDIUM: 91-180 days
     * LOW: > 180 days
     * UNKNOWN: Missing or invalid date
4. Provide replacement recommendation based on risk level

OUTPUT FORMAT (plain text, one section per device):
Device: <product_number>
Description: <product_description>
Location: <location>
Serial/PAK: <pak/serial_number>
Instance: <instance_number>
Quantity: <qty>
Support Ends: <last_date_of_support>
Days Until EOL: <exact days or N/A>
Risk Level: <CRITICAL|HIGH|MEDIUM|LOW|UNKNOWN>
Recommendation: <replacement or upgrade action>
Summary: <one-line device status and action>

CONSTRAINTS:
- Plain text only (no JSON, XML, tables, or code blocks)
- No extra explanations or summaries
- Count input and output records must match""")
    
    @staticmethod
    def _get_large_model_prompt() -> ChatPromptTemplate:
        """Optimized for large models (> 13B): Comprehensive with detailed instructions."""
        return ChatPromptTemplate.from_template("""You are an Enterprise Smart Network Device Migration support assistant.

ROLE INSTRUCTIONS:
You will receive device inventory data, replacement guidance, and user questions. Your task is to provide precise, actionable device migration recommendations based on end-of-life dates.

INPUTS:
DEVICE DATA: JSON array of device inventory records
  - Fields: product_description, location, pak/serial_number, instance_number, qty, last_date_of_support
REPLACEMENT GUIDANCE: {rag_context} - Rules and recommendations for device replacement strategies
USER QUESTION: {question} - Specific query about device migration needs
CURRENT DATE: {current_date} - Reference date for EOL calculations

DETAILED PROCESSING INSTRUCTIONS:

1. DATA VALIDATION
   - If DEVICE DATA is empty or contains no matching records, immediately output: "No devices found matching the criteria."
   - Parse device data exactly as provided without corrections or inferences
   - Do not attempt to repair or fill missing data

2. INDIVIDUAL DEVICE PROCESSING
   For each device record:
   
   a) Field Extraction (use exact values, no inference)
      - product_description: Device model/type
      - location: Physical location
      - pak/serial_number: Equipment identifier
      - instance_number: Service instance ID
      - qty: Quantity of devices
      - last_date_of_support: EOL date in YYYY-MM-DD format
   
   b) Days Until EOL Calculation (CRITICAL - use exact arithmetic)
      - Convert both dates to YYYY-MM-DD format
      - Calculate real calendar day count: (last_date_of_support - CURRENT_DATE)
      - If last_date_of_support < TODAY: Days Until EOL = 0 (already expired)
      - If last_date_of_support > TODAY: Days Until EOL = exact difference
      - If date missing/invalid: Days Until EOL = N/A
      - NEVER estimate or approximate dates
   
   c) Risk Level Assignment (based on days until EOL)
      - CRITICAL: EOL passed (days ≤ 0) or ≤ 30 days remaining
      - HIGH: 31-90 days until EOL
      - MEDIUM: 91-180 days until EOL
      - LOW: > 180 days until EOL
      - UNKNOWN: Missing or invalid date information
   
   d) Replacement Recommendation
      - Consult REPLACEMENT GUIDANCE for specific device recommendations
      - If guidance available: Use recommended replacement model
      - If no guidance: Suggest upgrade/migration based on risk level
      - For CRITICAL: Recommend immediate action
      - For HIGH: Recommend planning replacement within 60 days
      - For MEDIUM: Recommend budgeting for Q2/Q3 replacement
      - For LOW: Recommend scheduling for Q4 or next fiscal year

3. DATA QUALITY ASSURANCE
   - Ensure no data is fabricated or inferred
   - Only use information explicitly provided in DEVICE DATA
   - Mark uncertain values as N/A
   - Maintain exact field values from source data

OUTPUT SPECIFICATIONS:

Format: Plain text with one device section per record
Structure: One key-value pair per line, no JSON/XML/tables
Order: Process devices in same order as input

Per-Device Output:
Device: <product_number>
Description: <product_description>
Location: <location>
Serial/PAK: <pak/serial_number>
Instance: <instance_number>
Quantity: <qty>
Support Ends: <last_date_of_support>
Days Until EOL: <exact days or N/A>
Risk Level: <CRITICAL|HIGH|MEDIUM|LOW|UNKNOWN>
Recommendation: <specific replacement model or upgrade action>
Summary: <one-line device status with recommended action>

FINAL VALIDATION:
- Count all input device records
- Generate one output section per input record
- If counts do not match, regenerate the complete output
- Verify no data was invented or inferred
- Confirm all field values match source data exactly

DEVICE DATA: {sql_context}

Process now and provide complete analysis:""")


table_info = """
Table inventory has columns: s_no,product_number,product_description,last_date_of_support,pak/serial_number,instance_number,severity,parent_instance_number,service_level_description,sku,service_type,qty,umo,start_date,end_date,location
"""

# Legacy final_prompt for backward compatibility - will use medium optimization
final_prompt = ChatPromptTemplate.from_template("""ROLE: Your are Enterprise Smart Network Device Migration support assistant.

TASK:
- If DEVICE DATA is empty or null or empty array or NOT valid JSON -> output EXACTLY: "No devices found matching the criteria." and stop.   
- If DEVICE DATA is No SQL context available. -> output EXACTLY: "No devices found matching the criteria." and stop.                                                                                             
- DEVICE DATA is a JSON array of device records with fields: product_description, location, pak/serial_number, instance_number, qty, last_date_of_support, eol.
- For each device
   - Extract fields exactly as provided (no inference): product_description, location, pak/serial_number, instance_number, qty, last_date_of_support, eol
   - Don't attempt to correct or infer missing data. If a field is missing, mark it as N/A in the output.
   - Each device have unique instance number.
                                                                                                                                              
Calculate Risk Level based on eol:
- CRITICAL: eol passed or ≤ 30 days until EOL
- HIGH: 31-90 days until eol
- MEDIUM: 91-180 days until eol
- LOW: > 180 days until eol
- UNKNOWN: Missing or invalid date information

Example:
CURRENT_DATE: 2026-01-01
last_date_of_support: 2027-01-01
Days Until EOL: 365

Example:
CURRENT_DATE: 2026-05-06
last_date_of_support: 2026-05-05
Days Until EOL: 0
                                  
INPUTS:
DEVICE DATA: {sql_context}                                  
REPLACEMENT GUIDANCE: {rag_context}
USER QUESTION: {question}
CURRENT DATE: {current_date}

STRICT FORMAT RULES:
- Output must be plain text only.
- Do not use JSON, XML, YAML, tables, or code blocks.
- Do not use curly braces or square brackets.
- Do not add explanations, summaries, or extra text.
- Follow the exact format below.
- Input and output record counts must match. If not, regenerate the entire output.
- DO NOT include outside information or explanations. Only provide the device analysis as per the format below.
                                       

OUTPUT FORMAT (REPEAT FOR EACH DEVICE, following the same order as input):

**Instance <instance_number>** :
  Device: <product_number>
  Device Description: <product_description>                                                
  Location: <location>
  Serial/PAK: <pak/serial_number>
  Instance: <instance_number>
  Quantity: <qty>
  Support Ends: <last_date_of_support>
  Days Until EOL: <eol>
  Risk Level: <CRITICAL|HIGH|MEDIUM|LOW|UNKNOWN>
  Recommendation: <specific replacement model or upgrade action>
  Summary: <one-line device status with recommended action>
                                                                                               
(Leave one blank line between devices.)

FINAL CONSTRAINT:
- Plain text only
- No extra text before or after
- No JSON, tables, or code blocks
- Follow format exactly 
- Do not invent or infer any data not explicitly provided in DEVICE DATA""")

sql_prompt = PromptTemplate(
    input_variables=["input","table_info", "top_k", "current_date"],
    template="""You are a MySQL query builder. Convert the user request to a valid SQL SELECT query.

DATABASE SCHEMA:
{table_info}

CURRENT DATE:
{current_date}

QUERY RULES:
1. Use DATABASE SCHEMA to understand table structure and column names
2. Always: SELECT * FROM inventory i
3. Table alias: Use 'i' for inventory references (e.g., i.product_description)
4. Placeholders: Use %s for values, never hardcode them
5. LIKE searches: Add %% wildcards to params (%%search_term%%)
6. Dates: Format as YYYY-MM-DD
7. Relative date requests must stay dynamic. Use CURDATE() and DATE_ADD(...) or DATE_SUB(...) instead of hardcoded dates.
8. The inventory column last_date_of_support is stored as text in DD-MMM-YYYY format, so use STR_TO_DATE(i.last_date_of_support, '%d-%b-%Y') in date comparisons.
9. When the user asks for a window like "next 24 months", generate a date filter relative to CURDATE() and keep it parameter-free if possible.
10. End with: LIMIT {top_k}
11. NULL checks: Use IS NOT NULL (no %s placeholder)
12. Output: Two lines only - QUERY and PARAMS

EXAMPLES:

Request: "Find devices ending support before 2024-12-31"
QUERY: SELECT * FROM inventory i WHERE STR_TO_DATE(i.last_date_of_support, '%d-%b-%Y') < %s LIMIT {top_k}
PARAMS: 2024-12-31

Request: "Find devices where last_date_of_support is not null and is between today and 24 months from today"
QUERY: SELECT * FROM inventory i WHERE i.last_date_of_support IS NOT NULL AND STR_TO_DATE(i.last_date_of_support, '%d-%b-%Y') BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 24 MONTH) ORDER BY STR_TO_DATE(i.last_date_of_support, '%d-%b-%Y') ASC LIMIT {top_k}
PARAMS: 

Request: "List the devices which are at end of life"
QUERY: SELECT * FROM inventory i WHERE i.last_date_of_support IS NOT NULL AND STR_TO_DATE(i.last_date_of_support, '%d-%b-%Y') BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 24 MONTH) ORDER BY STR_TO_DATE(i.last_date_of_support, '%d-%b-%Y') ASC LIMIT {top_k}
PARAMS: 

Request: "which devices will support 4g feature?"
QUERY: SELECT * FROM inventory i WHERE i.product_description LIKE %s LIMIT {top_k}
PARAMS: %%4G%%

Request: "List all devices"
QUERY: SELECT * FROM inventory i LIMIT {top_k}
PARAMS: 

USER REQUEST: {input}

Output format (exactly two lines, no explanation):
QUERY: [SELECT statement]
PARAMS: [comma-separated values or empty]
""")