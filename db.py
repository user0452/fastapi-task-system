import pymysql


def get_conn():
    return pymysql.connect(
        host="127.0.0.1",
        user="root",
        password="pppp0000",
        database="task_db2",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )