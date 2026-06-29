from sqlalchemy import create_engine, text

engine = create_engine("mysql+pymysql://root:root@127.0.0.1:3306/inventory")
query = "SELECT instance_number, product_number, product_description, location, `pak/serial_number` AS serial, last_date_of_support FROM inventory WHERE STR_TO_DATE(last_date_of_support, '%d-%b-%Y') BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 24 MONTH) ORDER BY STR_TO_DATE(last_date_of_support, '%d-%b-%Y') ASC"
with engine.connect() as conn:
    rows = conn.execute(text(query)).fetchall()
    print('ROWS:', len(rows))
    for r in rows:
        print(r)
