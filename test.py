import pandas as pd
from sqlalchemy import create_engine
from app.config import MYSQL_URI
engine = create_engine(MYSQL_URI)
query = "SELECT * FROM inventory WHERE location = %s LIMIT 100"
params = ('Pune',)
df = pd.read_sql(query, engine, params=params)
print(df.head())