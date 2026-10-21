"""
PlantPulse AI — entry point.
Run with:  python app.py
Opens at:  http://127.0.0.1:5000
"""
import os

# config.py loads the .env located beside this entry point before defining
# Flask settings, regardless of the shell's current working directory.
from app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=app.config["DEBUG"])
