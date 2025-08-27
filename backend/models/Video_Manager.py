import gc
import subprocess
import time
import cv2
import psycopg2

class VideoManager:
    def __init__(self, lecture_name: str, video_name: str, video_id: int, video_path: str):
        self.lecture_name = lecture_name
        self.video_name = video_name
        self.video_path = video_path
        self.video_id = video_id

    def store_data(self, cursor):
        cap = cv2.VideoCapture(self.video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()

        sql = """
            INSERT INTO videos (id, lecture_name, video_name, fps, path)
            VALUES (%s, %s, %s, %s, %s)
        """

        try:
            cursor.execute(sql, (self.video_id, self.lecture_name, self.video_name, fps, self.video_path))
        except psycopg2.Error as e:
            print(f"Error inserting data for video {self.video_name}: {e}")
