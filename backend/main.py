import io
import math
from typing import List
import numpy as np
from pydantic import BaseModel
from PIL import Image
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import json

from .models.Database_Manager import DatabaseManager
from .services.cosine_sim import cosine_sim

app = FastAPI()

origins = [
    "http://localhost:5173",  # frontend URL and port
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# FRAME_DIR = "./backend/data/frames"
# LAYOUT_DIR = "./backend/data/layouts"
# VIDEO_DIR = "./backend/data/lecture_videos"

# Use absolute paths relative to this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

FRAME_DIR = os.path.join(DATA_DIR, "frames")
LAYOUT_DIR = os.path.join(DATA_DIR, "layouts")
VIDEO_DIR = os.path.join(DATA_DIR, "lecture_videos")
TRANSCRIPT_DIR = os.path.join(DATA_DIR, "transcripts")

# Serve the entire 'data' folder at /data URL prefix
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")


@app.get("/videos/{lecture_name}")
def get_available_videos(lecture_name: str):
    # connect to database
    connection, cursor = DatabaseManager.connect_to_database()

    sql = """
        SELECT id, video_name
        FROM videos
        WHERE lecture_name = %s
    """
    
    try:
        cursor.execute(sql, (lecture_name,))
        lecture_videos = cursor.fetchall()
        if lecture_videos is None:
            raise HTTPException(status_code=404, detail=f"Lecture '{lecture_name}' not found in database")

    except Exception as e:
        print(f"Couldn't retrieve data for lecture '{lecture_name}': {e}")
        cursor.connection.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    
    finally:
        cursor.close()
        connection.close()

    return [
        {
            "video_id": row[0],
            "video_name": row[1]
        }
        for row in lecture_videos
    ]


# "/video/{video_name}" is the endpoint that comes with a communication exchange when it's active
# here: GET request: recieving information from that endpoint
@app.get("/video/{lecture_name}/{video_id}")
def get_video(lecture_name: str, video_id: int):
    # connect to database
    connection, cursor = DatabaseManager.connect_to_database()
    
    sql = """
        SELECT path
        FROM videos
        WHERE lecture_name = %s AND id = %s
    """
    try:
        cursor.execute(sql, (lecture_name, video_id))
        result = cursor.fetchone()
        if result is None:
            raise HTTPException(status_code=404, detail=f"Video '{video_id}' not found in database")
        video_path = result[0]

    except Exception as e:
        print(f"Couldn't retrieve path information for video '{lecture_name}': {video_id}': {e}")
        cursor.connection.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    
    finally:
        cursor.close()
        connection.close()

    return RedirectResponse(video_path)


@app.get("/layout/{lecture_name}/{video_id}/{frame_index}")
def get_layout_data(lecture_name: str, video_id: int, frame_index: str):

    connection, cursor = DatabaseManager.connect_to_database()

    sql = """
        SELECT box_id, label, x1, y1, x2, y2
        FROM layouts
        WHERE lecture_name = %s AND video_id = %s AND frame_index = %s
        ORDER BY box_id
        """

    try:    
        cursor.execute(sql, (lecture_name, video_id, frame_index))
        box_rows = cursor.fetchall()
    except Exception as e:
        print(f"Couldn't retrieve layout information for video '{lecture_name}': {video_id}' at frame '{frame_index}': {e}")
        cursor.connection.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        cursor.close()
        connection.close()

    if not box_rows:
        raise HTTPException(status_code=404, detail="Layout data not found")

    return [
        {
            "box_id": row[0],
            "label": row[1],
            "coordinate": [row[2], row[3], row[4], row[5]]
        }
        for row in box_rows
    ]
    

@app.get("/fps/{lecture_name}/{video_id}")
def get_fps(lecture_name: str, video_id: int):
# connect to database
    connection, cursor = DatabaseManager.connect_to_database()
    
    sql = """
        SELECT fps
        FROM videos
        WHERE lecture_name = %s AND id = %s
    """
    try:
        cursor.execute(sql, (lecture_name, video_id))
        result = cursor.fetchone()
        if result is None:
            raise HTTPException(status_code=404, detail=f"Video '{lecture_name}': {video_id}' not found in database")
        fps = result[0]

    except Exception as e:
        print(f"Couldn't retrieve fps of video '{lecture_name}': {video_id}': {e}")
        cursor.connection.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    
    finally:
        cursor.close()
        connection.close()

    return {"fps": fps}
    

@app.get("/frames/metadata/{lecture_name}/{video_id}")
def get_available_frames(lecture_name: str, video_id: int):
    # Connect to database
    connection, cursor = DatabaseManager.connect_to_database()

    sql = """
        SELECT frame_index, width, height
        FROM frames
        WHERE lecture_name = %s AND video_id = %s
        ORDER BY frame_index
    """

    try:
        cursor.execute(sql, (lecture_name, video_id))
        frames_metadata = cursor.fetchall()

        if not frames_metadata:
            raise HTTPException(status_code=404, detail=f"No frames found for video '{lecture_name}': {video_id}'")

    except Exception as e:
        print(f"Couldn't retrieve frame indices for video '{lecture_name}': {video_id}': {e}")
        cursor.connection.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        cursor.close()
        connection.close()

    return [
        {
            "frame_index": row[0],
            "width": row[1],
            "height": row[2]
        }
        for row in frames_metadata
    ]
    

class ExplainRequest(BaseModel):
    lecture_name: str
    video_id: int
    frame_index: int
    box_id: int


@app.post("/explain")
async def explain(request: ExplainRequest):
    connection, cursor = DatabaseManager.connect_to_database()

    lecture_name = request.lecture_name
    video_id = request.video_id
    frame_index = request.frame_index
    box_id = request.box_id

    sql= """
        SELECT explanation, embedding
        FROM gpt_responses
        WHERE lecture_name = %s AND video_id = %s AND frame_index = %s AND box_id = %s
    """
    try:
        cursor.execute(sql, (lecture_name, video_id, frame_index, box_id))
        gpt_results = cursor.fetchone()
    except Exception as e:
        print("Error retrieving GPT data: {e}")
        cursor.connection.rollback()

    explanation, embedding = gpt_results
    
    return {
            "explanation": explanation,
            "embedding": embedding,
    }


class AssociateRequest(BaseModel):
    lecture_name: str
    video_id: int
    timestamp: float
    embedding: List[float]


@app.post("/associate")
async def associate_content(request: AssociateRequest):
    
    connection, cursor = DatabaseManager.connect_to_database()

    lecture_name = request.lecture_name
    video_id = request.video_id
    timestamp = request.timestamp
    explanation_embedding = request.embedding

    sql = """
        SELECT video_id, embedding, start_time, video_id
        FROM chunks
        WHERE lecture_name = %s AND
        (
          video_id < %s
          OR (video_id = %s AND start_time < %s)
        )
        ORDER BY video_id, chunk_index
    """

    try: 
        cursor.execute(sql, (lecture_name, video_id, video_id, timestamp))
        chunk_data = cursor.fetchall()
    
        video_ids_only = [row[0] for row in chunk_data]
        embeddings_only = [row[1] for row in chunk_data]
        start_times_only = [row[2] for row in chunk_data]
        filtered_embeddings = embeddings_only[:-4] if len(embeddings_only) > 4 else []

        # Match
        best_sim = -1
        sim_embedding_start_time = 0
        sim_embedding_video_id = None

        for index, chunk_embedding in enumerate(filtered_embeddings):
            sim = cosine_sim(np.array(explanation_embedding), np.array(chunk_embedding))
            if sim > best_sim:
                best_sim = sim
                sim_embedding_start_time = start_times_only[index]
                sim_embedding_video_id = video_ids_only[index]
                
        return {
            "start_time": sim_embedding_start_time,
            "video_id": sim_embedding_video_id
        }
    
    except Exception as e:
        print(f"Error retrieving prior transcript chunks : {e}")
        cursor.connection.rollback()
        raise HTTPException(status_code=500, detail="Failed to retrieve prior transcript chunks")
    finally:
        cursor.close()
        connection.close()









