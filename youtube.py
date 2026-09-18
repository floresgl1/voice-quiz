import re
from youtube_transcript_api import YouTubeTranscriptApi


def extract_video_id(url: str) -> str:
    patterns = [
        r'(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract video ID from URL: {url}")


def get_transcript(url: str) -> str:
    video_id = extract_video_id(url)
    ytt_api = YouTubeTranscriptApi()
    transcript = ytt_api.fetch(video_id)
    text = " ".join(snippet.text for snippet in transcript)
    if not text.strip():
        raise ValueError("Transcript is empty")
    return text
