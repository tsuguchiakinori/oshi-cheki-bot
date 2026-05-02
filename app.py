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
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.environ["CHANNEL_ACCESS_TOKEN"]
CHANNEL_SECRET = os.environ["CHANNEL_SECRET"]

BASE_URL = "https://oshi-cheki-bot.onrender.com"

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

user_texts = {}


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
    user_id = event.source.user_id
    user_message = event.message.text.strip()

    if user_message.startswith("テキスト"):
        text = user_message.replace("テキスト", "", 1).strip()
        if not text:
            text = "My Oshi"
        user_texts[user_id] = text

        reply = f"入れる文字を設定したで📸\n「{text}」\n次に画像送って！"
    elif "チェキ" in user_message:
        reply = "先に「テキスト 推し最高」みたいに送ってから、画像を送ってくれたらチェキ風にするで📸"
    else:
        reply = "「テキスト 好きな文字」を送ってから画像を送ってね📸"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    cheki_text = user_texts.get(user_id, "My Oshi")

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
    frame = Image.new("RGB", (900, 1120), "white")
    frame.paste(img, (50, 50))

    draw = ImageDraw.Draw(frame)

    # Noto Sans JPを使う
    # GitHubに NotoSansJP-Regular.ttf をアップしておくと反映される
    try:
        font = ImageFont.truetype("NotoSansJP-Regular.ttf", 48)
    except:
        font = ImageFont.load_default()

    # 文字を中央寄せ
    bbox = draw.textbbox((0, 0), cheki_text, font=font)
    text_width = bbox[2] - bbox[0]
    x = (900 - text_width) // 2
    y = 910

    draw.text((x, y), cheki_text, fill=(30, 30, 30), font=font)

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
