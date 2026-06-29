from sqlalchemy import create_engine, text
import re

engine = create_engine("mysql+pymysql://root:root@127.0.0.1:3306/inventory")
query = "SELECT * FROM inventory i WHERE i.last_date_of_support IS NOT NULL AND i.last_date_of_support BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 24 MONTH) ORDER BY i.last_date_of_support ASC LIMIT 3"
with engine.connect() as conn:
    col = conn.execute(text("SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='inventory' AND COLUMN_NAME='last_date_of_support'")).fetchone()
    print('COLUMN INFO:', col)
    query_exec = query
    if col and col[0] and col[0].lower() in ('text', 'varchar', 'char'):
        query_exec = re.sub(r"\blast_date_of_support\b", "STR_TO_DATE(last_date_of_support, '%d-%b-%Y')", query, flags=re.IGNORECASE)
    print('\nEXECUTING QUERY:\n', query_exec)
    rows = conn.execute(text(query_exec)).fetchall()
    print('\nRESULT ROWS COUNT:', len(rows))
    for r in rows:
        print(r)
