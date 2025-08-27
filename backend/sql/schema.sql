-- schema.sql

CREATE TABLE videos (
    id INTEGER, -- to store them in chronologic order
    lecture_name VARCHAR(100),
    video_name VARCHAR(300),
    fps REAL NOT NULL,
    path TEXT NOT NULL, -- https path
    PRIMARY KEY (id, lecture_name)
);

CREATE TABLE frames (
    video_id INTEGER,
    lecture_name VARCHAR(100),
    frame_index INTEGER,
    timestamp REAL,
    width INTEGER,
    height INTEGER,
    path TEXT,
    PRIMARY KEY (video_id, lecture_name, frame_index),
    FOREIGN KEY (video_id, lecture_name) REFERENCES videos(id, lecture_name)
);

CREATE TABLE transcripts (
    video_id INTEGER,
    lecture_name VARCHAR(100),
    transcript TEXT,
    language VARCHAR(20),
    PRIMARY KEY (video_id, lecture_name),
    FOREIGN KEY (video_id, lecture_name) REFERENCES videos(id, lecture_name)
);

CREATE TABLE segments (
    video_id INTEGER,
    lecture_name VARCHAR(100),
    segment_index INTEGER,
    start_time REAL,
    end_time REAL,
    text TEXT,
    PRIMARY KEY (video_id, lecture_name, segment_index),
    FOREIGN KEY (video_id, lecture_name) REFERENCES transcripts(video_id, lecture_name)
);

CREATE TABLE chunks (
    video_id INTEGER,
    lecture_name VARCHAR(100),
    chunk_index INTEGER,
    start_time REAL,
    end_time REAL,
    text TEXT,
    embedding DOUBLE PRECISION[],
    label TEXT,
    PRIMARY KEY (video_id, lecture_name, chunk_index),
    FOREIGN KEY (video_id, lecture_name) REFERENCES transcripts(video_id, lecture_name)
);

CREATE TABLE layouts (
    video_id INTEGER,
    lecture_name VARCHAR(100),
    frame_index INTEGER,
    box_id INTEGER,
    label VARCHAR(20),
    x1 REAL,
    y1 REAL,
    x2 REAL,
    y2 REAL,
    PRIMARY KEY (video_id, lecture_name, frame_index, box_id),
    FOREIGN KEY (video_id, lecture_name, frame_index) REFERENCES frames(video_id, lecture_name, frame_index)
);

CREATE TABLE gpt_responses (
    video_id INTEGER,
    lecture_name VARCHAR(100),
    frame_index INTEGER,
    box_id INTEGER,
    explanation TEXT,
    embedding DOUBLE PRECISION[],
    PRIMARY KEY (video_id, lecture_name, frame_index, box_id),
    FOREIGN KEY (video_id, lecture_name, frame_index, box_id) REFERENCES layouts (video_id, lecture_name, frame_index, box_id)
);
