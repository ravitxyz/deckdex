from typing import TypedDict, Optional

class TrackMetadata(TypedDict, total=False):
    title: str
    artist: str
    album: str
    year: Optional[int]
    genre: Optional[str]
    track_number: Optional[int]
    duration: Optional[float]
    bpm: Optional[float]
    key: Optional[str]
    energy: Optional[float]
