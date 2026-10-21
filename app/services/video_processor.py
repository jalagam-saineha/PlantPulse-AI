"""
Growth Studio video processing.

Runs in a background thread (no Celery/Redis — appropriate for a
single-user local college demo, per project decisions). Extracts frames
at a configurable sampling interval, runs the same computer-vision
measurement pipeline used by Leaf Analysis on each frame, and stores the
per-frame results plus overall video metadata.
"""
import threading
import uuid
from pathlib import Path

import cv2

from app.services.image_processor import analyze_leaf_array

# Guards against two processing jobs running for the same video at once,
# and lets routes check whether *any* job is currently active for a user.
_active_jobs = set()
_active_lock = threading.Lock()


def is_job_active(video_analysis_id: int) -> bool:
    with _active_lock:
        return video_analysis_id in _active_jobs


def probe_video(video_path: Path) -> dict:
    """Reads basic metadata (duration, fps, resolution) without full processing."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        cap.release()
        raise ValueError("Could not read the uploaded video. It may be corrupted or in an unsupported format.")

    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()

    duration = (frame_count / fps) if fps > 0 else 0.0
    return {
        "fps": round(fps, 2),
        "duration_seconds": round(duration, 1),
        "resolution": f"{width}x{height}" if width and height else None,
    }


def process_video_async(app, video_analysis_id: int) -> None:
    """Starts processing on a daemon background thread and returns immediately."""
    with _active_lock:
        _active_jobs.add(video_analysis_id)
    thread = threading.Thread(
        target=_process_video, args=(app, video_analysis_id), daemon=True
    )
    thread.start()


def _process_video(app, video_analysis_id: int) -> None:
    from app.extensions import db
    from app.models import VideoAnalysis, VideoFrame, TimelineEvent, Notification, User

    with app.app_context():
        video = db.session.get(VideoAnalysis, video_analysis_id)
        if video is None:
            with _active_lock:
                _active_jobs.discard(video_analysis_id)
            return

        video_path = Path(app.config["UPLOAD_VIDEOS_DIR"]) / video.video_path
        frames_dir = Path(app.config["RESULTS_FRAMES_DIR"])

        try:
            video.status = "PROCESSING"
            video.progress_percent = 0
            db.session.commit()

            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                raise ValueError("Could not open the video for processing.")

            fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            duration = (frame_count / fps) if fps > 0 else 0.0

            video.fps = round(fps, 2)
            video.duration_seconds = round(duration, 1)
            video.resolution = f"{width}x{height}" if width and height else None

            interval = video.sampling_interval_seconds or 5
            if duration <= 0:
                timestamps = [0.0]
            else:
                timestamps = list(_frange(0.0, duration, interval))
                if not timestamps:
                    timestamps = [0.0]

            total = len(timestamps)
            frames_dir.mkdir(parents=True, exist_ok=True)

            for idx, t in enumerate(timestamps):
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue

                metrics = analyze_leaf_array(frame)
                if metrics["leaf_area_px"] == 0:
                    # No foliage detected in this frame; skip storing a
                    # misleading zero-health record but keep processing.
                    video.progress_percent = int(100 * (idx + 1) / total)
                    db.session.commit()
                    continue

                from app.services.health_score import compute_health_score
                score = compute_health_score(metrics)

                frame_name = f"{uuid.uuid4().hex}_t{int(t)}.jpg"
                cv2.imwrite(str(frames_dir / frame_name), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])

                vf = VideoFrame(
                    video_analysis_id=video.id,
                    timestamp_seconds=round(t, 1),
                    frame_path=frame_name,
                    leaf_area_px=metrics["leaf_area_px"],
                    green_coverage=metrics["leaf_coverage"],
                    yellowing=metrics["yellowing"],
                    damage=metrics["damage"],
                    health_score=score["overall"],
                )
                db.session.add(vf)
                db.session.flush()

                db.session.add(TimelineEvent(
                    plant_id=video.plant_id,
                    source_type="video_frame",
                    source_id=vf.id,
                    event_date=video.created_at,
                    image_path=frame_name,
                    health_score=score["overall"],
                    leaf_area_px=metrics["leaf_area_px"],
                    yellowing=metrics["yellowing"],
                    damage=metrics["damage"],
                ))

                video.progress_percent = int(100 * (idx + 1) / total)
                db.session.commit()

            cap.release()

            video.status = "COMPLETED"
            video.progress_percent = 100
            from app.models.user import utcnow
            video.completed_at = utcnow()
            owner = db.session.get(User, video.user_id)
            if owner is None or owner.notifications_enabled:
                db.session.add(Notification(
                    user_id=video.user_id,
                    title="Growth scan completed",
                    message=f"Growth scan finished processing with {video.frames.count()} analyzed frame(s).",
                    link=f"/growth/{video.id}",
                ))
            db.session.commit()
            app.logger.info("Video analysis %s completed (%s frames)", video.id, video.frames.count())

        except Exception as exc:  # noqa: BLE001 - must not crash the background thread
            db.session.rollback()
            video = db.session.get(VideoAnalysis, video_analysis_id)
            if video is not None:
                video.status = "FAILED"
                video.error_message = str(exc)
                owner = db.session.get(User, video.user_id)
                if owner is None or owner.notifications_enabled:
                    db.session.add(Notification(
                        user_id=video.user_id,
                        title="Growth scan failed",
                        message=f"Processing failed: {exc}",
                        link=f"/growth/{video.id}",
                    ))
                db.session.commit()
            app.logger.error("Video analysis %s failed: %s", video_analysis_id, exc)
        finally:
            with _active_lock:
                _active_jobs.discard(video_analysis_id)


def _frange(start: float, stop: float, step: float):
    t = start
    while t < stop:
        yield t
        t += step
