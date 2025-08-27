import os
import psycopg2
from dotenv import load_dotenv

class DatabaseManager:

    def connect_to_database():        
        load_dotenv()

        connection = psycopg2.connect(
            host= os.getenv('DB_HOST'),
            port = os.getenv('DB_PORT'),
            database= os.getenv('DB_NAME'),
            user= os.getenv('DB_USER'),
            password= os.getenv('DB_PASSWORD')
        )        
        cursor = connection.cursor()

        return connection, cursor