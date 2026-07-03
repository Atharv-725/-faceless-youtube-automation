from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse
from typing import Optional
import edge_tts
import uuid
import subprocess
import os
import json
import textwrap

app = FastAPI()

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

@app.post("/tts")
async def tts(text: str, voice: str = "en-US-AriaNeural"):
    filename = f"/tmp/{uuid.uuid4()}.mp3"
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(filename)
    return FileResponse(filename, media_type="audio/mpeg")

@app.post("/render")
async def render(
    audio: UploadFile = File(...),
    image0: UploadFile = File(...),
    image1: Optional[UploadFile] = File(None),
    image2: Optional[UploadFile] = File(None),
    image3: Optional[UploadFile] = File(None),
    image4: Optional[UploadFile] = File(None),
    image5: Optional[UploadFile] = File(None),
    captions: Optional[str] = Form(None),
):
    images = [img for img in [image0, image1, image2, image3, image4, image5] if img is not None]

    job_id = str(uuid.uuid4())
    workdir = f"/tmp/{job_id}"
    os.makedirs(workdir, exist_ok=True)

    audio_path = f"{workdir}/audio.mp3"
    with open(audio_path, "wb") as f:
        f.write(await audio.read())

    duration_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", audio_path
    ]
    result = subprocess.run(duration_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"ffprobe failed: {result.stderr}")
    duration = float(json.loads(result.stdout)["format"]["duration"])

    per_image_duration = duration / len(images)
    for idx, img in enumerate(images):
        img_path = f"{workdir}/img_{idx:03d}.jpg"
        with open(img_path, "wb") as f:
            f.write(await img.read())

    concat_path = f"{workdir}/concat.txt"
    with open(concat_path, "w") as f:
        for idx in range(len(images)):
            f.write(f"file 'img_{idx:03d}.jpg'\n")
            f.write(f"duration {per_image_duration}\n")
        f.write(f"file 'img_{len(images)-1:03d}.jpg'\n")

    base_vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"

    if captions:
        try:
            caption_list = json.loads(captions)
        except Exception:
            caption_list = []

        drawtext_parts = []
        for idx, cap_text in enumerate(caption_list[:len(images)]):
            wrapped_text = textwrap.fill(cap_text, width=18)
            cap_file = f"{workdir}/cap_{idx}.txt"
            with open(cap_file, "w", encoding="utf-8") as f:
                f.write(wrapped_text)
            start = idx * per_image_duration
            end = (idx + 1) * per_image_duration
            drawtext_parts.append(
                f"drawtext=fontfile={FONT_PATH}:textfile={cap_file}:reload=0:"
                f"fontsize=42:fontcolor=white:borderw=5:bordercolor=black:"
                f"text_align=C:x=(w-text_w)/2:y=1500:line_spacing=10:"
                f"enable='between(t,{start},{end})'"
            )
        vf = base_vf + "," + ",".join(drawtext_parts)
    else:
        vf = base_vf

    output_path = f"{workdir}/output.mp4"
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_path,
        "-i", audio_path,
        "-vf", vf,
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        "-shortest",
        output_path
    ]
    result = subprocess.run(ffmpeg_cmd, cwd=workdir, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"ffmpeg failed: {result.stderr[-2000:]}")

    return FileResponse(output_path, media_type="video/mp4", filename="output.mp4")

@app.get("/health")
def health():
    return {"status": "ok"}
