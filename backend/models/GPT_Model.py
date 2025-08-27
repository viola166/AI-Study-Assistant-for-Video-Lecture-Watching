from io import BytesIO
import os
import numpy as np
from openai import OpenAI
from typing import List, Union
from pathlib import Path
from PIL import Image
import requests
from services.image_transform import pil_image_to_bytes
from services.transcript import get_context_chunks
import base64

class GPTModel:
    _instance = None

    def __init__(self):
        self.client = OpenAI()  # Uses OPENAI_API_KEY from SYTEM variables

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=texts
        )
        return [e.embedding for e in response.data]


    def cosine_sim(self, a: np.ndarray, b: np.ndarray) -> float:
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    

    def label_chunk(self, chunk_text: str) -> str:
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Label this transcript chunk concisely."},
                {"role": "user", "content": chunk_text}
            ]
        )
        return response.choices[0].message.content.strip()

    def _encode_image(self, image: Union[str, Path, bytes]) -> str:
        if isinstance(image, (str, Path)):
            with open(image, "rb") as f:
                image_data = f.read()
        elif isinstance(image, bytes):
            image_data = image
        else:
            raise ValueError("Image must be a file path or bytes.")

        return base64.b64encode(image_data).decode("utf-8")


    def explain(self, transcript: str, cropped_image: Union[str, Path, bytes], full_slide_image: Union[str, Path, bytes] = None) -> str:
        cropped_b64 = self._encode_image(cropped_image)
        images = [{
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{cropped_b64}"}
        }]

        if full_slide_image:
            slide_b64 = self._encode_image(full_slide_image)
            images.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{slide_b64}"}
            })

        # messages = [
        #     {
        #         "role": "user",
        #         "content": [
        #             {"type": "text", "text": (
        #                 "You are a concise tutor AI.\n"
        #                 "Image A: cropped region of a slide.\n"
        #                 "Image B: the complete slide containing that region.\n"
        #                 "Explain Image A clearly in 1–3 sentences, "
        #                 "using Image B and the transcript as context."
        #             )},
        #             {"type": "text", "text": f"Transcript:\n{transcript}"},
        #             {"type": "text", "text": "Image A:"},
        #             {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{cropped_b64}"}},
        #         ] + (
        #             [
        #                 {"type": "text", "text": "Image B:"},
        #                 {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{slide_b64}"}}
        #             ] if full_slide_image else []
        #         )
        #     }
        # ]

        messages = [
            # System sets behavior
            {
                "role": "system",
                "content": "You are a concise tutor AI. Explain the slide region in 3–5 sentences using all context."
            },
            # User provides task instruction
            {
                "role": "user",
                "content": (
                    "Explain the part of the slide provided in the second image using the full slide and transcript as context."
                    "Write the explanation in your own words. Use simple language. Do not mention images, slides, or sections; only explain the concepts shown."
                    "If and only if you have relevant knowledge beyond the transcript and slide that can help clarify or enrich the explanation, include it concisely."
                )
            },
            # User provides transcript
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "This is the transcript of lecture segment relevant to this slide. Use it for context."},
                    {"type": "text", "text": transcript}
                ]
            },
            # User provides the complete slide image
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "This image shows the complete slide for context."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{slide_b64}"}}
                ]
            },      
            # User provides cropped image
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "This image shows the specific part of the slide to explain."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{cropped_b64}"}}
                ]
            }

        ]


        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.45
        )

        return response.choices[0].message.content.strip()
    

    # method for creating all explanations for one specified video 
    def create_and_store_explanations(self, cursor, lecture_name, video_id):
        # if only storing explanations for one video
        
        sql_layouts = """
            SELECT * 
            FROM layouts
            WHERE lecture_name = %s AND video_id = %s
            ORDER BY frame_index, box_id
        """

        try:
            cursor.execute(sql_layouts, (lecture_name, video_id))
            result_layouts = cursor.fetchall()
        except Exception as e:
            print(f"Couldn't retrieve layout data: {e}")
            cursor.connection.rollback() 
        
        layouts = [
            {"frame_index": row[2], 
             "box_id": row[3], 
             "label": row[4],
             "coordinates": [row[5], row[6], row[7], row[8]]
            }
            for row in result_layouts
        ]

        sql_frames = """
            SELECT frame_index, timestamp, path
            FROM frames
            WHERE lecture_name = %s AND video_id = %s
            ORDER BY frame_index
        """
        try:
            cursor.execute(sql_frames, (lecture_name, video_id))
            result_frames = cursor.fetchall()
        except Exception as e:
            print(f"Couldn't retrieve frame data: {e}")
            cursor.connection.rollback()
        
        frames = [
            {"frame_index": row[0],
             "timestamp": row[1],
             "path": row[2]}
             for row in result_frames
        ]

        sql_chunks = """
            SELECT chunk_index, start_time, end_time, text
            FROM chunks
            WHERE lecture_name = %s AND video_id = %s
            ORDER BY chunk_index
        """
        try:
            cursor.execute(sql_chunks, (lecture_name, video_id))
            result_chunks = cursor.fetchall()
        except Exception as e:
            print(f"Couldn't retrieve chunk data: {e}")
            cursor.connection.rollback()

        chunks = [
            {"chunk_index": row[0],
             "start_time": row[1],
             "end_time": row[2],
             "text": row[3]}
             for row in result_chunks
        ]

        for index, frame_element in enumerate(frames):
            # get frame image
            #frame_img_path = os.path.join("..", frame_element["path"])
            response = requests.get(frame_element["path"])
            image = Image.open(BytesIO(response.content)).convert("RGB")
            
            # get the time frame in which the frame is showing
            lower_time_boundary = frame_element["timestamp"] / 1000         # miliseconds to seconds
            upper_time_boundary = (frames[index + 1]["timestamp"] / 1000 
                                   if len(frames) > index + 1 
                                   else chunks[-1]["end_time"]
                                   )

            context_text = get_context_chunks(chunks, lower_time_boundary, upper_time_boundary)
            
            # get all layouts that are within the current frame
            matching_layouts = []
            i = 0
            while i < len(layouts):
                if layouts[i]["frame_index"] == frame_element["frame_index"]:
                    matching_layouts.append(layouts.pop(i))  # Remove and collect
                else:
                    i += 1

            for layout_element in matching_layouts:
                x1, y1, x2, y2 = layout_element["coordinates"]
                cropped_box_image = image.crop((x1, y1, x2, y2))

                image_bytes = pil_image_to_bytes(image)
                cropped_image_bytes = pil_image_to_bytes(cropped_box_image)
                explanation = self.explain(transcript=context_text, cropped_image=cropped_image_bytes, full_slide_image=image_bytes)

                print(explanation)

                embedding = self.get_embeddings([explanation])[0]

                sql_gpt = """
                    INSERT INTO gpt_responses (lecture_name, video_id, frame_index, box_id, explanation, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """

                try: 
                    cursor.execute(sql_gpt, (lecture_name, video_id, frame_element["frame_index"], layout_element["box_id"], explanation, embedding))
                except Exception as e:
                    print(f"Couldn't store gpt responses: {e}")
                    cursor.connection.rollback() 
            

    # method for creating explanations for all videos in the table
    def create_and_store_all_explanations(self, cursor):
        sql = """
        SELECT id
        FROM videos
        """

        try:
            cursor.execute(sql, ())
            video_ids = cursor.fetchall()
        
        except Exception as e:
            print(f"Couldn't retrieve video names: {e}")
            cursor.connection.rollback()
        
        for video in video_ids:
            self.create_and_store_all_explanations(cursor, video)


        


        

        

