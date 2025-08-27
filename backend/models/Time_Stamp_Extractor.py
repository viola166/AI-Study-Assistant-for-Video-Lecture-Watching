import cv2
import os
import psycopg2.errors

# detecting time stamps of slide changes by comparing two neighbor frames each with their pixel-wise absolute difference
# lightweight approach: reducing image dimensions to 100x100
class TimeStampExtractor:

    def __init__(self, lecture_name, video_id: int, video_path: str, cursor, sample_rate=0.2, diff_threshold=2, resize_dim=(150, 85)):
        
        self.lecture_name = lecture_name
        self.video_path = video_path
        self.video_id = video_id
        self.cursor = cursor
        self.sample_rate = sample_rate  # frames per second to sample; default: every 5 seconds
        self.diff_threshold = diff_threshold
        self.resize_dim = resize_dim

        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            raise IOError(f"Cannot open video file: {self.video_path}")
        
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.frame_interval = int(self.fps / self.sample_rate) if self.sample_rate > 0 else 1

    def __del__(self):
        if self.cap.isOpened():
            self.cap.release()


    def _process_frame(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, self.resize_dim)
        return resized    


    def extract_timestamps_and_store(self):
        ret, prev_frame = self.cap.read()
        if not ret:
            raise ValueError("Cannot read video")

        prev_processed = self._process_frame(prev_frame)
        slide_change_frames = [0]  # first frame is a slide start
        frame_idx = 1

        while True:
            # Skip frames to sample at correct interval
            for _ in range(self.frame_interval - 1):
                if not self.cap.grab():
                    break

            ret, frame = self.cap.read()
            if not ret:
                break

            curr_processed = self._process_frame(frame)
            diff = cv2.absdiff(curr_processed, prev_processed)
            diff_mean = diff.mean()

            # print(frame_idx, diff_mean)

            if diff_mean > self.diff_threshold:
                slide_change_frames.append(frame_idx)
                sql = """
                    INSERT INTO frames (lecture_name, video_id, frame_index)
                    VALUES (%s, %s, %s)
                    """
                try:
                    self.cursor.execute(sql, (self.lecture_name, self.video_id, frame_idx))
                except psycopg2.errors.UniqueViolation:
                    print("This frame already exists, skipping or update if needed.")
                    self.cursor.connection.rollback()

            prev_processed = curr_processed
            frame_idx += self.frame_interval


        self.cap.release()

        return slide_change_frames
    
