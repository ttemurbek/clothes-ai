"""Local development server: `python -m backend` (http://127.0.0.1:5000)."""
import os

from .app import create_app

create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")),
                 debug=os.environ.get("FLASK_DEBUG") == "1")
