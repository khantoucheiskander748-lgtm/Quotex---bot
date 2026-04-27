from flask import Flask, jsonify, render_template, request

import bot

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    return jsonify(bot.state.to_dict())


@app.route("/api/start", methods=["POST"])
def api_start():
    started = bot.start_bot()
    return jsonify({"ok": started, "state": bot.state.to_dict()})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    stopped = bot.stop_bot()
    return jsonify({"ok": stopped, "state": bot.state.to_dict()})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    bot.state.reset_stats()
    return jsonify({"ok": True, "state": bot.state.to_dict()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)