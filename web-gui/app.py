#!/usr/bin/env python3
from flask import Flask, render_template, request, Response
from utils.logging_setup import setup_logging

# Configure logging before anything else
setup_logging()

from utils import config

# Import blueprints
from routes.containers import containers_bp
from routes.profiles import profiles_bp
from routes.auth import auth_bp
from routes.rebuild import rebuild_bp

app = Flask(__name__)

# Register blueprints
app.register_blueprint(containers_bp)
app.register_blueprint(profiles_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(rebuild_bp)


def check_auth():
    """Before-request hook: enforce Basic Auth if credentials are configured."""
    if not config.AUTH_USERNAME or not config.AUTH_PASSWORD:
        return  # No auth configured, allow all
    auth = request.authorization
    if not auth or auth.username != config.AUTH_USERNAME or auth.password != config.AUTH_PASSWORD:
        return Response(
            'Authentication required', 401,
            {'WWW-Authenticate': 'Basic realm="Google Photos Sync Manager"'}
        )


app.before_request(check_auth)


@app.route('/')
def index():
    """Main dashboard"""
    return render_template('index.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
