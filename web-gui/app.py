#!/usr/bin/env python3
from flask import Flask, render_template

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


@app.route('/')
def index():
    """Main dashboard"""
    return render_template('index.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
