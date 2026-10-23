from fastapi import APIRouter, Request, UploadFile, File, Response
from fastapi.responses import StreamingResponse
from app.services.video_streamer import video_streamer

router = APIRouter(prefix="/video", tags=["Video Streaming"])

@router.get("/stream", summary="Live MJPEG video stream")
async def video_stream():
    """
    Continuous multipart MJPEG stream for real-time video monitoring.
    Can be used directly in HTML: <img src="/api/v1/video/stream" />
    """
    return StreamingResponse(
        video_streamer.generate_mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@router.get("/frame", summary="Get single latest video frame")
def get_frame():
    """
    Returns the latest single JPEG frame from camera.
    """
    frame = video_streamer.get_latest_frame()
    return Response(content=frame, media_type="image/jpeg")

@router.post("/frame", summary="Upload camera frame from robot or simulator")
async def upload_frame(request: Request):
    """
    Receives raw JPEG image bytes directly in HTTP request body.
    """
    body = await request.body()
    if body:
        video_streamer.update_frame(body)
        return {"status": "ok", "size": len(body)}
    return {"status": "empty"}

@router.post("/upload", summary="Upload camera frame as multipart form")
async def upload_multipart_frame(file: UploadFile = File(...)):
    """
    Receives camera frame as multipart file upload.
    """
    data = await file.read()
    video_streamer.update_frame(data)
    return {"status": "ok", "size": len(data)}
