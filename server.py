from flask import Flask, request, jsonify, send_from_directory
from main import reconcile_data

app = Flask(__name__)


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/reconcile", methods=["POST"])
def reconcile_endpoint():
    tx_file = request.files.get("transactions")
    bank_file = request.files.get("bank_balances")

    if not tx_file or not bank_file:
        return jsonify({"error": "Both files are required"}), 400

    tx_text = tx_file.read().decode("utf-8")
    bank_text = bank_file.read().decode("utf-8")

    try:
        result = reconcile_data(tx_text, bank_text)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)
