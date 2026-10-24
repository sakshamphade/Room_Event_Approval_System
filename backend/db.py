
import os
import mysql.connector


def get_db_connection():
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.environ["DB_PASSWORD"],
        database=os.getenv("DB_NAME", "event_area_approval")
    )
    return connection


if __name__ == "__main__":
    connection = get_db_connection()

    if connection.is_connected():
        print("MySQL Database Connected Successfully!")

    connection.close()
