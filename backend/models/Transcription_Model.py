import subprocess
import tempfile
import psycopg2
import whisper
import os

class WhisperTranscriber:
    def __init__(self, lecture_name, video_id, video_path, model_size="base"):
        """
        Initialize the Whisper model.
        
        Args:
            model_size (str): One of ["tiny", "base", "small", "medium", "large"]
        """
        print(f"Loading Whisper model: {model_size}")
        self.model = whisper.load_model(model_size)
        self.video_path = video_path
        self.video_id = video_id
        self.lecture_name = lecture_name


    def transcribe_and_store(self, cursor):
        """
        Transcribes or translates an audio/video file.

        Args:
            file_path (str): Path to the audio/video file
            language (str): Optional, force transcription language (e.g., 'en')
            task (str): "transcribe" or "translate"

        Returns:
            dict: Full result with text and segments
        """
        print(f"Transcribing file: {self.video_path}")
        

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_wav_path = tmp_file.name

        # Convert video to WAV
        subprocess.run(
            ["ffmpeg", "-y", "-i", self.video_path, "-ar", "16000", "-ac", "1", tmp_wav_path],
            check=True
        )
        
        result = self.model.transcribe(tmp_wav_path, language="en", task="transcribe")

        # Remove temp file manually
        os.remove(tmp_wav_path)
        
        full_text = result.get("text")
        transcript_language = result.get("language")

        # Store in PostgreSQL
        # full transcript
        sql = """
            INSERT INTO transcripts (lecture_name, video_id, transcript, language)
            VALUES (%s, %s, %s, %s)
            """
        try:
            cursor.execute(sql, (self.lecture_name, self.video_id, full_text, transcript_language))
        except psycopg2.errors.UniqueViolation:
            print(f"Transcript for '{self.video_id}' already exists. Skipping insert.")
            cursor.connection.rollback()

        # segments of transcript
        segments = result.get("segments", [])
        for segment in segments:
            segment_index = segment.get("id")
            start_time = segment.get("start")
            end_time = segment.get("end")
            segment_text = segment.get("text")
            
            sql = """
                INSERT INTO segments (lecture_name, video_id, segment_index, start_time, end_time, text)
                VALUES (%s, %s, %s, %s, %s, %s)
                """
            try:
                cursor.execute(sql, (self.lecture_name, self.video_id, segment_index, start_time, end_time, segment_text))

            except psycopg2.errors.UniqueViolation:
                print(f"Segment {segment_index} for '{self.video_id}' already exists. Skipping.")
                cursor.connection.rollback()
        
        return result

    

    def get_text(self, file_path):
        """
        Returns only the text portion of the transcript.
        
        Args:
            file_path (str): Path to the audio/video file

        Returns:
            str: Transcribed text
        """
        result = self.model.transcribe(file_path)
        return result.get("text", "")
    
    
    def get_text_by_frame_ranges(self, segments, frame_ranges, fps):
        """
        Given Whisper segments and a list of (start_frame, end_frame) tuples,
        return grouped transcriptions per slide interval.
        """
        grouped_transcripts = []

        for start_frame, end_frame in frame_ranges:
            start_time = start_frame / fps
            end_time = end_frame / fps

            segment_text = ""
            for segment in segments:
                if segment['start'] >= start_time and segment['start'] < end_time:
                    segment_text += segment['text'].strip() + " "

            grouped_transcripts.append({
                'start_frame': start_frame,
                'end_frame': end_frame,
                'start_time': start_time,
                'end_time': end_time,
                'text': segment_text.strip()
            })

        return grouped_transcripts
    

    def get_transcript_for_pause_frame(self, video_path, pause_frame, slide_changes, fps, full_transcript = None):
        index = 0
        while index < len(slide_changes) and slide_changes[index] < pause_frame:
            index += 1

        # maybe modify to using the previous + next frame as well
        # now: using two frames before + one frame after
        upper_boundary = slide_changes[index+1] if index+1 < len(slide_changes) else int(self.result["segments"][-1]["end"] * fps)
        lower_boundary = slide_changes[index - 3] if index-3 >= 0 else 0

        frame_range = [(lower_boundary, upper_boundary)]

        if full_transcript != None:
            full_transcript = self.transcribe(video_path)
        segments = full_transcript["segments"]
        
        return self.get_text_by_frame_ranges(segments, frame_range, fps)[0]["text"]
    

    def save_transcript_to_file(self, text, output_path):
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)

