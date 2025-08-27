// File: frontend/src/App.tsx
import { useState, useRef, useEffect } from 'react'
import './App.css'

interface Box {
  label: string
  coordinate: [number, number, number, number]
  box_id: number
}

interface LayoutData {
  layout: {
    boxes: Box[]
  }
}

interface FrameMeta {
  frame_index: number
  width: number
  height: number
}

interface VideoKeys {
  id: number
  video_name: string
}

// component: App
function App() {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [allFramesMetaData, setAllFramesMetaData] = useState<FrameMeta[]>([]);
  const [displayedVideoSize, setDisplayedVideoSize] = useState<{ width: number; height: number }>({ width: 640, height: 360 })
  const [showGotIt, setShowGotIt] = useState(false);
  const [timeBeforeJump, setTimeBeforeJump] = useState<number | null>(null)
  const [videoIDBeforeJump, setVideoIDBeforeJump] = useState<number | null>(null)
  const [hoveredBoxId, setHoveredBoxId] = useState<number | null>(null)
  const [selectedExplanation, setSelectedExplanation] = useState<string | null>(null);
  const [selectedExplanationEmbedding, setSelectedExplanationEmbedding] = useState<number[] | null>(null)
  const [showExplain, setShowExplain] = useState(false)
  const [lastBoxCoordinates, setLastBoxCoordinates] = useState<number[] | null>(null)
  const [fps, setFps] = useState<number>(25) 
  const [layoutData, setLayoutData] = useState<LayoutData | null>(null)
  const [videoID, setVideoID] = useState<number>(0)
  const [lectureName, setLectureName] = useState<String | null>("Introduction to Artificial Intelligence 2021")
  const [availableLectureVideos, setAvailableLectureVideos] = useState<VideoKeys[]>([]);
  const jumpTimestampRef = useRef<number | null>(null);
  

  useEffect(() => {
    const fetchAvailableVideos = async () => {
      try {
        const res = await fetch(`/videos/${lectureName}`);
        const rawLectureVideos = await res.json() as Array<{ video_id: string; video_name: string }>;

        // Convert id to number if it's a string
        const lectureVideos: VideoKeys[] = rawLectureVideos.map(video => ({
          id: Number(video.video_id),
          video_name: video.video_name
        }));

        setAvailableLectureVideos(lectureVideos);
      } catch (err) {
        console.error("Failed to fetch available video IDs:", err);
      }
    };

    fetchAvailableVideos();
  }, [lectureName]);


  useEffect(() => {
    const fetchInitialData = async () => {
      try {
        
        const videoRes = await fetch(`/fps/${lectureName}/${videoID}`)
        const fpsJson = await videoRes.json()
        const fps = Number(fpsJson.fps)
        console.log(fps)
        setFps(fps || 25)

        console.log("fetched video fps")

        const frameRes = await fetch(`/frames/metadata/${lectureName}/${videoID}`)
        const rawFramesMetaData = await frameRes.json() as Array<{ frame_index: string, width: string, height: string }>;

        const framesMetaData: FrameMeta[] = rawFramesMetaData.map(frame => ({
          frame_index: Number(frame.frame_index),
          width: Number(frame.width),
          height: Number(frame.height),
        }));

        setAllFramesMetaData(framesMetaData);

        console.log("fetched frames' metadata")
      } catch (err) {
        console.error("Failed to load video fps or frames' metadata:", err)
      }
    };

    fetchInitialData();

    const video = videoRef.current;
    if (jumpTimestampRef.current !== null && video) {
      const targetTime = jumpTimestampRef.current;
      const onLoadedMetadata = () => {
        video.currentTime = targetTime!;
        video.play();
        video.removeEventListener("loadedmetadata", onLoadedMetadata);
        jumpTimestampRef.current = null; // reset after use
      };

      if (video.readyState >= 1) {
        // already loaded -> seek immediately
        video.currentTime = targetTime!;
        video.play();
        jumpTimestampRef.current = null;
      } else {
        video.addEventListener("loadedmetadata", onLoadedMetadata);
      }

    }
  }, [videoID]);


  useEffect(() => {
    console.log("layoutData updated:", layoutData)
  }, [layoutData])

  
  const getCurrentFrameIndex = () => {
    const video = videoRef.current
    if (!video) return
    
    const frameIndices = allFramesMetaData.map(frame => frame.frame_index);
    console.log(frameIndices)

    const current_index = Math.floor(video.currentTime * fps)
    let i = 0
    while (i < frameIndices.length && frameIndices[i] < current_index) {
      i += 1
    }

    const next_available_index = frameIndices[i] ?? frameIndices[frameIndices.length - 1]

    return next_available_index
  }


  // event handler function onPause; defined within App component
  const onPause = async () => {
    const video = videoRef.current
    if (!video) return

    const next_available_index = getCurrentFrameIndex()
    if (!next_available_index) return
    
    console.log(next_available_index)   

    const rect = video.getBoundingClientRect()
    setDisplayedVideoSize({ width: rect.width, height: rect.height })
    
    let frameWidth = 1920 // default
    const currentFrameMetaData = allFramesMetaData.find(meta => meta.frame_index === next_available_index);
    if (currentFrameMetaData)
      frameWidth = currentFrameMetaData.width
    const scale = displayedVideoSize.width / frameWidth

    try {
      const res = await fetch(`/layout/${lectureName}/${videoID}/${next_available_index}`)
      const layoutJson = await res.json()

      const simpleBoxes: Box[] = layoutJson.map((box: any) => {
        const [x1, y1, x2, y2] = box.coordinate
        return {
          box_id: box.box_id,
          label: box.label,
          coordinate: [
            x1 * scale,
            y1 * scale,
            x2 * scale,
            y2 * scale
          ],
        }
      })

      if (layoutJson) {
        setLayoutData({
          layout: { boxes: simpleBoxes }
        })
      }

    } catch (err) {
      console.error("Failed to fetch layout data:", err)
    }

  }

  const getCurrentTimestamp = () => {
    return videoRef.current ? videoRef.current.currentTime : 0;
  }

  const jumpTo = (new_video_id: number, timestamp: number) => {

    console.log("Jumping to", new_video_id, timestamp);

    if (videoID !== new_video_id) {
      jumpTimestampRef.current = timestamp;
      setVideoID(new_video_id);
    } else {
      const video = videoRef.current;
      if (!video) return;
      // if already loaded, just seek
      if (video.readyState >= 1) {
        video.currentTime = timestamp;
        video.play();
      } else {
        const onLoadedMetadata = () => {
          video.currentTime = timestamp;
          video.play();
          video.removeEventListener("loadedmetadata", onLoadedMetadata);
        };
        video.addEventListener("loadedmetadata", onLoadedMetadata);
      }
    }
  };

  // after "Explain" Button Click (or indirectly after "Show Context" Button Click)
  const fetchExplanation = async (box_id: number, box_coordinate: number[], clickedExplain: boolean) => {

    if (selectedExplanation && selectedExplanationEmbedding && lastBoxCoordinates === box_coordinate)
      return selectedExplanation
    
    const currentFrame = getCurrentFrameIndex()

    const explainResponse = await fetch(`/explain`, {
      method: "POST",
      headers: { 
        "Content-Type": "application/json" 
      },
      body: JSON.stringify({ 
        lecture_name: lectureName,
        video_id: videoID, 
        frame_index: currentFrame, 
        box_id: box_id 
      }),
    });

    if (!explainResponse.ok) throw new Error("Failed to fetch explanation");

    const gptData = await explainResponse.json();
    const explanation = gptData.explanation
    const embedding = gptData.embedding

    setSelectedExplanation(explanation);
    setSelectedExplanationEmbedding(embedding)
    setLastBoxCoordinates(box_coordinate)
    if (!showExplain)                         // if the explanation panel is currently not shown
      setShowExplain(clickedExplain)          // show it if user asked for explanation; don't show it if not
                                              // if the explanation panel is currently shown, don't change anything
    return explanation
  };


  // after "Show Context" Button Click
  const handleShowContext = async (box_id: number, box_coordinate: number[], timestamp: number) => {
    try {
      const clickedExplain = false      // user clicked on "show context", not "explain"

      await fetchExplanation(box_id, box_coordinate, clickedExplain); // not fetching the explanation, just ensuring selectedExplanationEmbedding is not null

      const matchResponse = await fetch("/associate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lecture_name: lectureName,
          video_id: videoID,
          timestamp: timestamp,
          embedding: selectedExplanationEmbedding,
        }),
      });

      if (!matchResponse.ok) throw new Error("Failed to match explanation to previous transcript");

      const matchData = await matchResponse.json();
      const context_video = matchData.video_id;
      const context_start_time = matchData.start_time;
      console.log("Matched chunk starts at:", matchData);
      // Do something useful with context...
      
      setVideoIDBeforeJump(videoID)
      setTimeBeforeJump(timestamp)    // buffer for coming back
      
      jumpTo(context_video, context_start_time)

      setShowGotIt(true)

    } catch (error) {
      console.error("Error while fetching context:", error);
    }
  };

  const onGotItClick = () => {

    if (videoIDBeforeJump === null || timeBeforeJump === null) {
      setShowGotIt(false);
      return;
    }

    jumpTimestampRef.current = Math.max(0, timeBeforeJump - 5);

    if (videoID !== videoIDBeforeJump) {
      setVideoID(videoIDBeforeJump); // The useEffect above will handle jumping
    } else if (videoRef.current) {
      videoRef.current.currentTime = jumpTimestampRef.current;
      videoRef.current.play();
      jumpTimestampRef.current = null;
    }

    setShowGotIt(false);
  };

  return (
    <div className="main-layout">
      {/* Sidebar for selecting videos */}
      <div className="video-sidebar">
        <h3>Lecture Videos</h3>
        <ul>
          {availableLectureVideos.map((video) => (
            <li key={video.id}>
              <button
                className={videoID === video.id ? 'selected' : ''}
                onClick={() => setVideoID(video.id)}
                data-fulltext={video.video_name}
                title={video.video_name} // fallback for tooltip
              >
                {video.video_name}
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div className='main-container'>
        <div className='video-container'>
          <video className='video-player'
            key={videoID}
            ref={videoRef}
            width="640"
            controls
            onPause={onPause}
            onPlay={() => {
              setLayoutData(null)
              setHoveredBoxId(null)
            }}
            style={{ display: 'block' }}
          >
            <source src={`/video/${lectureName}/${videoID}`} type="video/mp4" />
          </video>

          {layoutData && (
            <div className="layout-overlay">
              {layoutData.layout.boxes.map((box, idx) => (
                <div className="overlay-box"
                  key={idx}
                  style={{
                    top: box.coordinate[1],
                    left: box.coordinate[0],
                    width: box.coordinate[2] - box.coordinate[0],
                    height: box.coordinate[3] - box.coordinate[1],
                  }}
                  onMouseEnter={() => setHoveredBoxId(box.box_id)}
                  onMouseLeave={() => setHoveredBoxId(null)}
                >
                  {hoveredBoxId === box.box_id && (
                    <div className='overlay-highlight'>
                      <div className='button-background'
                          style = {{
                            width: displayedVideoSize.width * 0.15,
                            height: displayedVideoSize.height * 0.15,
                          }}
                      >
                        <button className='Get-AI-Mentor'
                          onClick={(e) => {
                            e.stopPropagation();
                            fetchExplanation(box.box_id, box.coordinate, true);
                          }}
                        >
                          Explain
                        </button>
                        <button className='Get-AI-Mentor'
                          onClick={(e) => {
                            e.stopPropagation();
                            handleShowContext(box.box_id, box.coordinate, getCurrentTimestamp());
                          }}
                        >
                          Show Context
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {showGotIt && (
            <button className='navigator-button'
              onClick={onGotItClick}
            >
              Got it!
            </button>
          )}
        </div>
        {selectedExplanation && showExplain && (
          <div className="chat-panel"
            style= {{
              height: displayedVideoSize.height - 30,     /* -30 because of padding 15px*/
            }}
          >
            <div className="chat-header">
              <h3>AI Mentor</h3>
              <button onClick={() => {setSelectedExplanation(null), setShowExplain(false)}}>✕</button>
            </div>
            <p>{selectedExplanation}</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default App
