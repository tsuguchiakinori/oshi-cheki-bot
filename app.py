import os
from flask import Flask, request, abort, send_file
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    ImageMessage,
    TextSendMessage,
    ImageSendMessage,
)

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.environ["CHANNEL_ACCESS_TOKEN"]
CHANNEL_SECRET = os.environ["CHANNEL_SECRET"]

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)


@app.route("/", methods=["GET"])
def home():
    return "OK"


@app.route("/input.jpg", methods=["GET"])
def send_input_image():
    return send_file("/tmp/input.jpg", mimetype="image/jpeg")


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_message = event.message.text

    if "チェキ" in user_message:
        reply = "推しチェキいいね！📸✨"
    else:
        reply = f"{user_message} って言ったね！"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    message_id = event.message.id

    message_content = line_bot_api.get_message_content(message_id)

    with open("/tmp/input.jpg", "wb") as f:
        for chunk in message_content.iter_content():
            f.write(chunk)

    line_bot_api.reply_message(
        event.reply_token,
        ImageSendMessage(
            original_content_url="https://oshi-cheki-bot.onrender.com/input.jpg",
            preview_image_url="https://oshi-cheki-bot.onrender.com/input.jpg"
        )
    )
