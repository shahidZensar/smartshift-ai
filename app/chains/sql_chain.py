import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from langchain_core.output_parsers import StrOutputParser
from langchain_community.utilities import SQLDatabase

from ..models import QueryRequest
from ..config import CONVERSTIONAL_MEMORY_PROMPT, MYSQL_URI, RAG_INDEX_PATH
from .. import logger
from ..util import clean_sql, final_prompt, json_serializer, safe_text, sql_prompt, table_info, format_sql_response, with_history
from ..decision import openai_llm

async def sql_chain(request: QueryRequest, history: str = "") -> str:
        engine = create_engine(MYSQL_URI)
        db = SQLDatabase(engine)
        sql_context:str = "No SQL context available."
        df = {}
        current_date = pd.Timestamp.now().normalize().strftime("%Y-%m-%d")
        sql_response = await openai_llm.ainvoke(
            with_history(
                sql_prompt.format(
                    input=safe_text(request.question),
                    table_info=table_info,
                    top_k=3,
                    current_date=current_date
                ),
                history,
            )
        )
        #logger.info(f"SQL response from LLM: %r", sql_response)
        sql_query = sql_response.content if hasattr(sql_response, 'content') else sql_response
        logger.info("Raw SQL query from LLM: %r", sql_query)  # Log the raw SQL query before cleaning
        sql_query = StrOutputParser().parse(sql_query)
        logger.info("Generated SQL query: %r", sql_query)  # Log the raw SQL query before cleaning
        #sql_query = json.loads(sql_query)
        query, params = format_sql_response(sql_query)
        logger.info("After JSON format Generated SQL query: %r & params %r", query, params)
        try:
            logger.info("Executing SQL query against database:%r", query.lower())
            if query:
                query = query.replace("%d-%b-%Y", "%%d-%%b-%%Y")
                logger.info("fetching all records from inventory table as fallback")
                df = pd.read_sql(query, engine, params=params)
                df[df.select_dtypes(include="number").columns] = df.select_dtypes(include="number").fillna(0).astype("Int64")
                
                # Calculate Days Until EOL before converting dates to strings
                today = pd.Timestamp.now().normalize()
                df['eol'] = df.apply(
                    lambda row: (pd.Timestamp(row['last_date_of_support']) - today).days 
                    if pd.notnull(row['last_date_of_support']) 
                    else ((pd.Timestamp(row['end_date']) - today).days if pd.notnull(row['end_date']) else None),
                    axis=1
                )
                date_cols = df.select_dtypes(include=['datetime', 'datetimetz']).columns
                df[date_cols] = df[date_cols].apply(lambda x: x.dt.strftime('%Y-%m-%d'))
                logger.info("SQL query executed successfully, retrieved %d records", len(df))
            if isinstance(df, pd.DataFrame) and len(df.index) > 0:
                logger.info("SQL query returned results, using SQL context for answer generation")
                try:
                    logger.info("Serializing SQL context for LLM input")
                    sql_context = df.to_json(orient="records", date_format="iso")
                except Exception as e:
                    logger.error("Error serializing SQL context: %s",   e)
            return sql_context if sql_context else "No data found matching the criteria."         
        except Exception as e:
            logger.error("Error executing SQL query: %s",   e) 
            return "No data found matching the criteria."
        