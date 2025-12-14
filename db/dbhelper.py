import sqlite3
import os
from sqlite3 import Error

database = os.path.join(os.path.dirname(__file__), "Avila.db")

def getprocess(sql: str, vals: list = []) -> list:
    try:
        conn = sqlite3.connect(os.path.abspath(database))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql, vals)
        data = cursor.fetchall()
        conn.close()
        return data
    except Error as e:
        print("Error:", e)
        return []

def postprocess(sql: str, vals: list = []) -> bool:
    try:
        conn = sqlite3.connect(os.path.abspath(database))
        cursor = conn.cursor()
        cursor.execute(sql, vals)
        conn.commit()
        conn.close()
        return True
    except Error as e:
        print("Error:", e)
        return False

# --- THE FIX: Updated getall to accept order_by ---
def getall(table: str, order_by: str = None) -> list:
    """Fetches all records from a table, with optional sorting."""
    sql = f"SELECT * FROM {table}"
    # Append the ORDER BY clause if a value is provided
    if order_by:
        sql += f" ORDER BY {order_by}"
        
    return getprocess(sql, [])
# --- END OF FIX ---

def getrecord(table: str, **kwargs) -> list:
    keys = list(kwargs.keys())
    vals = list(kwargs.values())
    fields = " AND ".join([f"{k}=?" for k in keys])
    sql = f"SELECT * FROM {table} WHERE {fields}"
    return getprocess(sql, vals)

def addrecord(table: str, **kwargs) -> bool:
    keys = list(kwargs.keys())
    vals = list(kwargs.values())
    fields = ",".join(keys)
    qmarks = ",".join(["?" for _ in vals])
    sql = f"INSERT INTO {table} ({fields}) VALUES ({qmarks})"
    return postprocess(sql, vals)

def deleterecord(table: str, **kwargs) -> bool:
    keys = list(kwargs.keys())
    vals = list(kwargs.values())
    fields = " AND ".join([f"{k}=?" for k in keys])
    sql = f"DELETE FROM {table} WHERE {fields}"
    return postprocess(sql, vals)

def updaterecord(table: str, data: dict, **kwargs) -> bool:
    set_part = ", ".join([f"{k}=?" for k in data.keys()])
    where_part = " AND ".join([f"{k}=?" for k in kwargs.keys()])
    sql = f"UPDATE {table} SET {set_part} WHERE {where_part}"
    vals = list(data.values()) + list(kwargs.values())
    return postprocess(sql, vals)