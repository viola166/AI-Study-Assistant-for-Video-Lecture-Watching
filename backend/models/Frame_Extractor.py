import os
import cv2
import psycopg2
from supabase import create_client, Client

class FrameExtractor:
    def __init__(self, lecture_name: str, video_id: int, video_path: str):
        self.lecture_name = lecture_name
        self.video_id = video_id
        self.video_path = video_path
        self.supabase_key = os.getenv('SUPABASE_KEY')
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_bucket_name = os.getenv('SUPABASE_BUCKET_NAME')

        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)

        self.cap = cv2.VideoCapture(self.video_path)
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)


    def get_frames_and_store(self, cursor, frame_indices):
        

        for idx in frame_indices:
            
            if not self.cap.isOpened():
                print(f"Warning: Could not open video at frame {idx}")
            # Convert frame index to milliseconds using fps
            timestamp_ms = (idx / self.fps) * 1000
            self.cap.set(cv2.CAP_PROP_POS_MSEC, timestamp_ms)
            success, frame = self.cap.read()

            if success:

                success, buffer = cv2.imencode('.png', frame)
                if not success:
                    print(f"Warning: Could not encode frame {idx} to PNG")
                    continue
                png_bytes = buffer.tobytes()

                # Construct the remote path inside the bucket, e.g., "video_name/idx.png"
                remote_path = f"{self.lecture_name}/{self.video_id}/frames/{idx}.png"
                remote_path_corrected = remote_path.replace(" ", "%20")

                full_url = f"{self.supabase_url}/storage/v1/object/public/{self.supabase_bucket_name}/{remote_path_corrected}"

                # Upload to Supabase Storage
                response = self.supabase.storage.from_(self.supabase_bucket_name).upload(remote_path_corrected, png_bytes, file_options={"content-type": "image/png",})

                print(response)

                height, width = frame.shape[:2]
                sql = """
                    UPDATE frames
                    SET timestamp = %s,
                        path = %s,
                        width = %s,
                        height = %s
                    WHERE video_id = %s AND frame_index = %s
                    """
                
                try: 
                    cursor.execute(sql, (timestamp_ms, full_url, width, height, self.video_id, idx))
                except psycopg2.Error as e:
                    print(f"psycopg2 error while updating DB for frame {idx}: {e.pgerror}")
                    cursor.connection.rollback()

            else:
                print(f"Warning: Failed to read frame at index {idx} (timestamp: {timestamp_ms} ms)")

        self.cap.release()

        
        return f"Uploaded frames to Supabase bucket '{self.supabase_bucket_name}' in folder '{self.lecture_name}/{self.video_id}/frames'"
