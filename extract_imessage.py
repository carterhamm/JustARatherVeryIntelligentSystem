import sqlite3
import pandas as pd
import os
import datetime

def get_imessage_data(db_path=None):
    if not db_path:
        db_path = os.path.expanduser("~/Library/Messages/chat.db")

    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return None

    # Connect to the database
    # Note: Accessing ~/Library/Messages/chat.db usually requires Full Disk Access
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.OperationalError as e:
        print(f"Error connecting to database: {e}")
        print("CRITICAL: Your Terminal/IDE needs 'Full Disk Access' in System Settings > Privacy & Security to read this file.")
        return None

    # SQL query to join message, handle, and chat tables
    # Timestamps in iMessage are typically nanoseconds since 2001-01-01
    query = """
    SELECT
        message.rowid,
        message.date AS timestamp_nanos,
        message.text,
        message.is_from_me,
        handle.id AS sender_handle,
        chat.chat_identifier
    FROM
        message
    LEFT JOIN handle ON message.handle_id = handle.rowid
    LEFT JOIN chat_message_join ON message.rowid = chat_message_join.message_id
    LEFT JOIN chat ON chat_message_join.chat_id = chat.rowid
    WHERE
        message.text IS NOT NULL
    ORDER BY
        message.date DESC
    LIMIT 5000
    """

    try:
        df = pd.read_sql_query(query, conn)
        conn.close()
    except Exception as e:
        print(f"Error executing query: {e}")
        return None

    # Convert timestamp
    # Mac epoch starts on 2001-01-01
    mac_epoch = datetime.datetime(2001, 1, 1)
    
    def convert_date(ts):
        try:
            # timestamp is in nanoseconds, convert to seconds
            return mac_epoch + datetime.timedelta(seconds=ts/1000000000)
        except Exception:
            return None

    df['formatted_date'] = df['timestamp_nanos'].apply(convert_date)
    
    # Clean up dataframe
    df['sender'] = df.apply(lambda row: 'Me' if row['is_from_me'] == 1 else row['sender_handle'], axis=1)
    
    return df

if __name__ == "__main__":
    print("Attempting to extract iMessage history...")
    print("Note: If this fails with 'OperationalError: attempt to write a readonly database' or similar permissions errors, grant Full Disk Access to your terminal.")
    
    df = get_imessage_data()
    
    if df is not None and not df.empty:
        print(f"Successfully extracted {len(df)} messages.")
        print("\nSample Data:")
        print(df[['formatted_date', 'sender', 'text']].head())
        
        # Save to CSV for ingestion into Vector DB
        output_file = "imessage_export.csv"
        df.to_csv(output_file, index=False)
        print(f"\nSaved export to {output_file}")
    else:
        print("No data extracted.")
