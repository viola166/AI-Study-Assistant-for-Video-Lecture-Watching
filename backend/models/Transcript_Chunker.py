import numpy as np
from typing import List, Dict

import psycopg2
from models.GPT_Model import GPTModel
from models.Database_Manager import DatabaseManager

class TranscriptChunker:
    def __init__(self, lecture_name, video_id, embed_model: str = "text-embedding-3-small", similarity_threshold: float = 0.26):
        self.lecture_name = lecture_name
        self.video_id = video_id
        self.embed_model = embed_model
        self.similarity_threshold = similarity_threshold
        self.client = GPTModel.get_instance()  # Create OpenAI client


    def chunk_transcript_and_store(self, cursor, enrich_with_gpt: bool = False) -> List[Dict]:
        """
        Takes a list of Whisper-style transcript segments and returns semantic chunks.
        Each segment should have: {"start": float, "end": float, "text": str}
        """

        sql = """
            SELECT start_time, end_time, text
            FROM segments
            WHERE lecture_name = %s AND video_id = %s
            ORDER BY start_time
            """

        try: 
            cursor.execute(sql, (self.lecture_name, self.video_id))
            rows = cursor.fetchall()
        except psycopg2.Error as e:
            print(f"Query failed: {e}")
            cursor.connection.rollback() 
        

        # 2. Format into transcript_segments
        transcript_segments = [
            {"start": row[0], "end": row[1], "text": row[2]}
            for row in rows
        ]

        if not transcript_segments:
            return []

        texts = [seg["text"] for seg in transcript_segments]
        embeddings = self.client.get_embeddings(texts)

        chunks = []
        current_chunk = {
            "start": transcript_segments[0]["start"],
            "end": transcript_segments[0]["end"],
            "text": transcript_segments[0]["text"],
        }

        for i in range(1, len(transcript_segments)):
            sim = self.client.cosine_sim(embeddings[i], embeddings[i - 1])

            # if the similarity between the two segments is lower than the threshold,
            # then they are not chunked together and a new chunk begins
            if sim < self.similarity_threshold:
                if enrich_with_gpt:
                    current_chunk["label"] = self.client.label_chunk(current_chunk["text"])
               
                chunk_embedding = list(self.client.get_embeddings([current_chunk["text"]])[0])
                current_chunk["embedding"] = chunk_embedding
                chunks.append(current_chunk)

                # store in Postgres

                sql = """
                    INSERT INTO chunks (lecture_name, video_id, chunk_index, start_time, end_time, text, embedding, label)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """
                try:
                    cursor.execute(sql, (self.lecture_name, self.video_id, len(chunks)-1, current_chunk["start"], current_chunk["end"], current_chunk["text"], current_chunk["embedding"], current_chunk["label"]))
                    
                except psycopg2.errors.UniqueViolation:
                    print(f"Segment {len(chunks)-1} for '{self.video_id}' already exists. Skipping.")
                    cursor.connection.rollback()

                current_chunk = {
                    "start": transcript_segments[i]["start"],
                    "end": transcript_segments[i]["end"],
                    "text": transcript_segments[i]["text"],
                    "label": None,
                }
            else:
                current_chunk["end"] = transcript_segments[i]["end"]
                current_chunk["text"] += " " + transcript_segments[i]["text"]

        # Add final chunk
        if enrich_with_gpt:
            current_chunk["label"] = self.client.label_chunk(current_chunk["text"])
        
        chunk_embedding = list(self.client.get_embeddings([current_chunk["text"]])[0])
        current_chunk["embedding"] = chunk_embedding
        chunks.append(current_chunk)

        # store in Postgres
        sql = """
            INSERT INTO chunks (lecture_name, video_id, chunk_index, start_time, end_time, text, embedding, label)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """     
        try:
            cursor.execute(sql, (self.lecture_name, self.video_id, len(chunks)-1, current_chunk["start"], current_chunk["end"], current_chunk["text"], current_chunk["embedding"], current_chunk["label"]))
            
        except psycopg2.errors.UniqueViolation:
            print(f"Segment {len(chunks)-1} for '{self.video_id}' already exists. Skipping.")
            cursor.connection.rollback()

        return chunks


        # get the current transcript chunk, the five previous ones, and the 5 next ones
    def get_chunks_for_pause(self, cursor, timestamp: float) -> str:
        """
        Returns up to 9 chunks: 4 before, the current, and 4 after the chunk containing the timestamp.
        """
        
        sql_index = """
            SELECT chunk_index
            FROM chunks
            WHERE lecture_name = %s AND video_id = %s AND start_time < %s AND end_time >= %s
            ORDER BY chunk_index
            LIMIT 1
        """

        sql_chunks = """
            SELECT text
            FROM chunks
            WHERE lecture_name = %s AND video_id = %s AND chunk_index BETWEEN %s AND %s
            ORDER BY chunk_index
        """

        try:
            # Step 1: Find the index of the chunk that includes the timestamp
            cursor.execute(sql_index, (self.lecture_name, self.video_id, timestamp, timestamp))

            row = cursor.fetchone()
            if not row:
                return ""

            current_chunk_index = row[0]

            # Step 2: Retrieve surrounding chunks (4 before, current, 4 after)
            start_index = max(0, current_chunk_index - 4)
            end_index = current_chunk_index + 4  # PostgreSQL will return fewer if out of bounds

            cursor.execute(sql_chunks, (self.lecture_name, self.video_id, start_index, end_index))

            chunk_texts = [row[0] for row in cursor.fetchall()]
            return " ".join(chunk_texts)

        except Exception as e:
            print(f"Error retrieving chunks for video '{self.video_id}': {e}")
            cursor.connection.rollback()




