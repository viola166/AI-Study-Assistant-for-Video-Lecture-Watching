import json
import os
from typing import List, Dict

from fastapi import HTTPException
from models.Database_Manager import DatabaseManager  # Make sure this exists and connects properly

def get_context_chunks(chunks: List[Dict], lower_time_boundary: float, upper_time_boundary: float):
    # get the transcript chunks that are laying within the time frame
    i = 0
    while i < len(chunks) and chunks[i]["start_time"] < lower_time_boundary:
        i += 1
    lowest_chunk_index = chunks[i-1]["chunk_index"]

    i = lowest_chunk_index
    while i < len(chunks) and chunks[i]["start_time"] <= upper_time_boundary:
        i += 1
    heighest_chunk_index = chunks[i-1]["chunk_index"]

    # additionally get the 4 previous and the 2 next transcript chunk
    lowest_chunk_index_new = max(0, lowest_chunk_index - 4)
    heighest_chunk_index_new = min(len(chunks) - 1, heighest_chunk_index + 2)

    context_chunks = chunks[lowest_chunk_index_new : heighest_chunk_index_new + 1]
    context_text = " ".join(chunk["text"] for chunk in context_chunks)

    return context_text
            

# # get the current transcript chunk, the five previous ones, and the 5 next ones
# def get_transcript_chunks_for_pause(video_name: str, timestamp: float) -> str:
#     """
#     Returns up to 9 chunks: 4 before, the current, and 4 after the chunk containing the timestamp.
#     """

#     connection, cursor = DatabaseManager.connect_to_database()
    
#     sql_index = """
#         SELECT chunk_index
#         FROM chunks
#         WHERE video_name = %s AND start_time < %s AND end_time >= %s
#         ORDER BY chunk_index
#         LIMIT 1
#     """

#     sql_chunks = """
#         SELECT text
#         FROM chunks
#         WHERE video_name = %s AND chunk_index BETWEEN %s AND %s
#         ORDER BY chunk_index
#     """

#     try:
#         # Step 1: Find the index of the chunk that includes the timestamp
#         cursor.execute(sql_index, (video_name, timestamp, timestamp))

#         row = cursor.fetchone()
#         if not row:
#             return ""

#         current_chunk_index = row[0]

#         # Step 2: Retrieve surrounding chunks (4 before, current, 4 after)
#         start_index = max(0, current_chunk_index - 4)
#         end_index = current_chunk_index + 4  # PostgreSQL will return fewer if out of bounds

#         cursor.execute(sql_chunks, (video_name, start_index, end_index))

#         chunk_texts = [row[0] for row in cursor.fetchall()]
#         return " ".join(chunk_texts)

#     except Exception as e:
#         print(f"Error retrieving chunks for video '{video_name}': {e}")
#         cursor.connection.rollback()
#         raise HTTPException(status_code=500, detail="Failed to retrieve transcript chunks")

#     finally:
#         cursor.close()
#         connection.close()

