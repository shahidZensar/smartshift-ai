from sqlalchemy import create_engine, text

def inspect():
    engine = create_engine("mysql+pymysql://root:root@127.0.0.1:3306/inventory")
    with engine.connect() as conn:
        cols = conn.execute(text("SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='inventory' AND TABLE_NAME='inventory'"))
        print('COLUMNS:')
        for c in cols:
            print(c)
        print('\nSAMPLES:')
        rows = conn.execute(text("SELECT last_date_of_support, CAST(last_date_of_support AS CHAR) AS aschar, LENGTH(CAST(last_date_of_support AS CHAR)) AS len FROM inventory LIMIT 10"))
        for r in rows:
            print(r)

if __name__ == '__main__':
    inspect()
