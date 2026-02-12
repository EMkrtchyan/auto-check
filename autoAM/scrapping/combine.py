import sqlite3
import pandas as pd

# ---------------------------------------------------------
# 1. SETUP DATABASE CONNECTION
# ---------------------------------------------------------
db_filename = 'database2.db' # Replace with your DB file path
conn = sqlite3.connect(db_filename)

try:
    print(f"Connected to {db_filename}...")

    # ---------------------------------------------------------
    # 2. EXTRACT DATA
    # ---------------------------------------------------------
    # read_sql_query works natively with sqlite3 connections
    df_cars = pd.read_sql_query("SELECT * FROM cars", conn)
    df_tags = pd.read_sql_query("SELECT * FROM tags", conn)

    # ---------------------------------------------------------
    # 3. TRANSFORM (Pivot Tags)
    # ---------------------------------------------------------
    print("Pivoting tags...")
    
    # Turn rows into columns
    df_tags_pivoted = df_tags.pivot_table(
        index='car_id', 
        columns='attribute', 
        values='value', 
        aggfunc='first' # Handle duplicates if any exist
    ).reset_index()

    # ---------------------------------------------------------
    # 4. MERGE (Join Tables)
    # ---------------------------------------------------------
    print("Merging tables...")
    
    df_unified = pd.merge(
        df_cars, 
        df_tags_pivoted, 
        left_on='id', 
        right_on='car_id', 
        how='left'
    )

    # Clean up duplicate id column from the merge
    if 'car_id' in df_unified.columns:
        df_unified.drop(columns=['car_id'], inplace=True)

    # ---------------------------------------------------------
    # 5. LOAD (Create New Table)
    # ---------------------------------------------------------
    new_table_name = "unified_cars"
    print(f"Saving to new table '{new_table_name}'...")

    # Pandas to_sql natively supports sqlite3 connection objects
    df_unified.to_sql(
        new_table_name, 
        conn, 
        if_exists='replace', 
        index=False
    )

    print("Success! Data unified.")
    print(df_unified.head())

except Exception as e:
    print(f"Error: {e}")

finally:
    # Always close the connection
    conn.close()