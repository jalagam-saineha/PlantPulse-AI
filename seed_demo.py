"""
PlantPulse AI — optional demo data seeder.

Run manually (never automatic):

    python seed_demo.py

Creates one demo account with a couple of plants and a real leaf analysis
(computed with the actual OpenCV pipeline on a generated sample image —
not fabricated numbers). Everything created here is clearly labeled
"(Demo)" so it's obvious what can be deleted, and the script is safe to
run more than once (it won't duplicate the demo account).
"""
import sys
from datetime import date, timedelta

import cv2
import numpy as np

from app import create_app
from app.extensions import db
from app.models import User, Plant, Analysis, TimelineEvent, Notification
from app.services.image_processor import analyze_leaf_image
from app.services.health_score import compute_health_score

DEMO_EMAIL = "demo@plantpulse.local"
DEMO_PASSWORD = "demo12345"


def _make_synthetic_leaf(path, healthy: bool):
    img = np.full((500, 500, 3), (235, 235, 230), dtype=np.uint8)
    cv2.ellipse(img, (250, 250), (190, 140), 0, 0, 360, (40, 150, 40), -1)
    if not healthy:
        cv2.ellipse(img, (190, 210), (70, 50), 15, 0, 360, (30, 200, 220), -1)  # yellow
        cv2.ellipse(img, (320, 270), (55, 40), -10, 0, 360, (40, 70, 110), -1)  # brown
        cv2.circle(img, (250, 180), 14, (20, 20, 20), -1)  # dark spot
    cv2.imwrite(str(path), img)


def main():
    app = create_app()
    with app.app_context():
        existing = User.query.filter_by(email=DEMO_EMAIL).first()
        if existing:
            print(f"[DEMO DATA] Demo account already exists ({DEMO_EMAIL}). Nothing to do.")
            print("To start fresh, delete the account from the app, or delete instance/plantpulse.db entirely.")
            return 0

        user = User(name="Demo User (Demo)", email=DEMO_EMAIL)
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        db.session.flush()

        plant_a = Plant(
            user_id=user.id, name="Demo Tomato (Demo)", species="Tomato", variety="Roma",
            planting_date=date.today() - timedelta(days=21),
            location="Demo Greenhouse Bay 1",
            notes="DEMO DATA — safe to delete. Created by seed_demo.py.",
        )
        plant_b = Plant(
            user_id=user.id, name="Demo Basil (Demo)", species="Basil",
            planting_date=date.today() - timedelta(days=10),
            location="Demo Greenhouse Bay 2",
            notes="DEMO DATA — safe to delete. Created by seed_demo.py.",
        )
        db.session.add_all([plant_a, plant_b])
        db.session.flush()

        # --- One real (healthy-looking) analysis for the tomato plant ---
        images_dir = app.config["UPLOAD_IMAGES_DIR"]
        processed_dir = app.config["RESULTS_PROCESSED_DIR"]
        images_dir.mkdir(parents=True, exist_ok=True)

        src_path = images_dir / "demo_seed_leaf.jpg"
        _make_synthetic_leaf(src_path, healthy=True)
        metrics, processed_name, overlay_name = analyze_leaf_image(src_path, processed_dir)
        score = compute_health_score(metrics)

        analysis = Analysis(
            user_id=user.id, plant_id=plant_a.id,
            original_image=src_path.name, processed_image=processed_name, overlay_image=overlay_name,
            status="completed",
            leaf_coverage=metrics["leaf_coverage"], yellowing=metrics["yellowing"],
            damage=metrics["damage"], dark_spots=metrics["dark_spots"],
            affected_area=metrics["affected_area"], leaf_area_px=metrics["leaf_area_px"],
            health_score=score["overall"],
        )
        db.session.add(analysis)
        db.session.flush()

        db.session.add(TimelineEvent(
            plant_id=plant_a.id, source_type="analysis", source_id=analysis.id,
            event_date=analysis.created_at, image_path=processed_name,
            health_score=score["overall"], leaf_area_px=metrics["leaf_area_px"],
            yellowing=metrics["yellowing"], damage=metrics["damage"],
        ))
        db.session.add(Notification(
            user_id=user.id, title="Analysis completed (Demo)",
            message=f'Leaf analysis for "{plant_a.name}" scored {score["overall"]}/100.',
            link=f"/analyze/{analysis.id}",
        ))

        db.session.commit()

        print("[DEMO DATA] Demo account created.")
        print(f"  Email:    {DEMO_EMAIL}")
        print(f"  Password: {DEMO_PASSWORD}")
        print("  2 demo plants created, 1 real Leaf Analysis run on a generated sample image.")
        print("  Everything is labeled '(Demo)' and can be deleted from within the app.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
