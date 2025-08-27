import json
import tempfile
import time
import requests
from models.Layout_Model import LayoutModel
from models.Time_Stamp_Extractor import TimeStampExtractor
from models.Frame_Extractor import FrameExtractor
from models.Transcription_Model import WhisperTranscriber
from models.Transcript_Chunker import TranscriptChunker
from models.GPT_Model import GPTModel
from models.Image_Cropper import ImageCropper
from models.Video_Manager import VideoManager
from models.Database_Manager import DatabaseManager
import os


# CONNECT TO DATABASE 
connection, cursor = DatabaseManager.connect_to_database()

#### Program #### 

script_dir = os.path.dirname(os.path.abspath(__file__))

# create directories for data
data_output_dir = "data"
all_frames_output_dir = os.path.join(data_output_dir, "frames")             # stores all extracted jpg frames from the videos

lectures_data_path = os.path.join(script_dir, data_output_dir, "lectures_old.json")

with open(lectures_data_path, "r", encoding="utf-8") as f:
    lectures_data = json.load(f)

for lecture in lectures_data:

    for index, video in enumerate(lecture["videos"]):
        if index == 0:
            print("drin")
            lecture_name = lecture["lecture"]
            lecture_video_name = video["video_name"]


            headers = {
                "Cookie": "JSESSIONID=node01ddxo7huujd5sufziwqk9ck2q8109666.node0",
            }

            response = requests.get(video["path"], headers=headers, stream=False)
            if response.status_code != 200:
                raise Exception(f"Failed to download video from {video['path']}, status code: {response.status_code}")

            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        temp_file.write(chunk)
                temp_file.flush()
                temp_path = temp_file.name


                videoManager = VideoManager(lecture_name = lecture_name, video_name=lecture_video_name, video_path=temp_file.name, video_id=video["id"])
                videoManager.store_data(cursor)

                try:
                    connection.commit()
                    print("video manager changes commited successfully")

                except Exception as e:
                    connection.rollback()  # Optional: undo changes on failure
                    print("An error occurred while commiting video manager changes, rolled back:", e)

                # Use temp_file.name as the path to the file
                # extract the time stamps (frame indices) at which the slides are changing
                timeExtractor = TimeStampExtractor(lecture_name=lecture_name, video_id=video["id"], video_path=temp_file.name, cursor=cursor, sample_rate = 0.2)
                slideChanges = timeExtractor.extract_timestamps_and_store()

                try:
                    connection.commit()
                    print("time extractor changes commited successfully")

                except Exception as e:
                    connection.rollback()  # Optional: undo changes on failure
                    print("An error occurred while commiting time extractor changes, rolled back:", e)

                # extract the frames at the previoiusly defined indices
                frameExtractor = FrameExtractor(lecture_name=lecture_name, video_id=video["id"], video_path=temp_file.name)
                frameExtractor.get_frames_and_store(cursor, slideChanges)             # frame indices implicitly casted to miliseconds

                try:
                    connection.commit()
                    print("frame extractor changes commited successfully")

                except Exception as e:
                    connection.rollback()  # Optional: undo changes on failure
                    print("An error occurred while commiting frame extractor changes, rolled back:", e)



            # run layout detection model and store png + json results
            layoutDetector = LayoutModel(cursor=cursor, lecture_name=lecture_name, video_id = video["id"])
            layoutDetector.run_and_store_all_frames(cursor)

            try:
                connection.commit()
                print("layout detector changes commited successfully")

            except Exception as e:
                connection.rollback()  # Optional: undo changes on failure
                print("An error occurred while commiting layout detector changes, rolled back:", e)           
           
           
            # extract the complete transcript in the preprocessing step
            try:
                transcriber = WhisperTranscriber(lecture_name=lecture_name, video_id=video["id"], video_path=temp_path)
                full_transcript = transcriber.transcribe_and_store(cursor)

            finally:
                # Delete the temp file manually afterwards
                time.sleep(1)

                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
            try:
                connection.commit()
                print("transcriber changes commited successfully")

            except Exception as e:
                connection.rollback()
                print("An error occurred while commiting transcriber changes, rolled back:", e)

            # chunk the transcript for embedding purpose
            chunker = TranscriptChunker(lecture_name=lecture_name, video_id = video["id"])
            chunks = chunker.chunk_transcript_and_store(cursor, enrich_with_gpt=True)

            try:
                connection.commit()
                print("transcript chunker changes commited successfully")

            except Exception as e:
                connection.rollback()
                print("An error occurred while commiting transcript chunker changes, rolled back:", e)

 
            gpt_model = GPTModel.get_instance()
            gpt_model.create_and_store_explanations(cursor, lecture_name=lecture_name, video_id=video["id"])

            try:
                connection.commit()
                print("GPT model changes commited successfully")

            except Exception as e:
                connection.rollback()
                print("An error occurred while commiting GPT model changes, rolled back:", e)



cursor.close()
connection.close()