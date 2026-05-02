import os
import time
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
from PIL import Image

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.environ["CHANNEL_ACCESS_TOKEN"]
CHANNEL_SECRET = os.environ["CHANNEL_SECRET"]

BASE_URL = "https://oshi-cheki-bot.onrender.com"

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)


@app.route("/", methods=["GET"])
def home():
    return "OK"


@app.route("/output.jpg", methods=["GET"])
def output_image():
    return send_file("/tmp/output.jpg", mimetype="image/jpeg")


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
        reply = "写真送ってくれたらチェキ風にするで📸"
    else:
        reply = f"{user_message} って言ったね！"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    message_content = line_bot_api.get_message_content(event.message.id)

    with open("/tmp/input.jpg", "wb") as f:
        for chunk in message_content.iter_content():
            f.write(chunk)

    img = Image.open("/tmp/input.jpg").convert("RGB")

    # 中央正方形トリミング
    w, h = img.size
    size = min(w, h)
    left = (w - size) // 2
    top = (h - size) // 2
    img = img.crop((left, top, left + size, top + size))
    img = img.resize((800, 800))

    # チェキ風フレーム
    frame = Image.new("RGB", (900, 1100), "white")
    frame.paste(img, (50, 50))
    frame.save("/tmp/output.jpg", quality=95)

    cache_buster = int(time.time())
    image_url = f"{BASE_URL}/output.jpg?v={cache_buster}"

    line_bot_api.reply_message(
        event.reply_token,
        ImageSendMessage(
            original_content_url=image_url,
            preview_image_url=image_url
        )
    )
