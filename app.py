import os
import time
import random
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
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.environ["CHANNEL_ACCESS_TOKEN"]
CHANNEL_SECRET = os.environ["CHANNEL_SECRET"]
BASE_URL = "https://oshi-cheki-bot.onrender.com"

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

user_texts = {}
user_dates = {}

# =========================
# 共通
# =========================
def load_font(size):
    try:
        return ImageFont.truetype("makiirclehand.ttf", size)
    except:
        return ImageFont.load_default()

def apply_cheki_filter(img):
    img = ImageEnhance.Color(img).enhance(0.9)
    img = ImageEnhance.Contrast(img).enhance(1.1)
    img = img.filter(ImageFilter.GaussianBlur(0.3))
    return img

# =========================
# route
# =========================
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

# =========================
# テキスト処理
# =========================
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()

    if msg.startswith("テキスト"):
        text = msg.replace("テキスト", "").strip()
        if not text:
            text = "My Oshi"
        user_texts[user_id] = text
        reply = f"文字を設定したで📸\n「{text}」\n次に画像送って！"

    elif msg.startswith("日付"):
        date = msg.replace("日付", "").strip()
        if not date:
            date = "2026.01.01"
        user_dates[user_id] = date
        reply = f"日付を設定したで📅\n「{date}」"

    else:
        reply = "「テキスト ○○」「日付 2026.3.29」って送ってから画像送ってな📸"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

# =========================
# 画像処理
# =========================
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id

    text = user_texts.get(user_id, "My Oshi")
    date = user_dates.get(user_id, "")

    # 画像取得
    message_content = line_bot_api.get_message_content(event.message.id)
    with open("/tmp/input.jpg", "wb") as f:
        for chunk in message_content.iter_content():
            f.write(chunk)

    img = Image.open("/tmp/input.jpg").convert("RGB")

    # 正方形トリミング
    w, h = img.size
    size = min(w, h)
    img = img.crop(((w-size)//2, (h-size)//2, (w+size)//2, (h+size)//2))

    # リサイズ
    img = img.resize((900, 900))

    # チェキ風フィルター
    img = apply_cheki_filter(img)

    # フレーム
    frame = Image.new("RGB", (1000, 1300), "#f7f5f2")
    frame.paste(img, (50, 80))

    draw = ImageDraw.Draw(frame)

    # フォント
    text_font = load_font(70)
    date_font = load_font(40)

    # 中央配置
    text_bbox = draw.textbbox((0, 0), text, font=text_font)
    text_w = text_bbox[2] - text_bbox[0]

    date_bbox = draw.textbbox((0, 0), date, font=date_font)
    date_w = date_bbox[2] - date_bbox[0]

    # 描画位置
    text_x = (1000 - text_w) // 2
    date_x = (1000 - date_w) // 2

    # 描画
    draw.text((text_x, 1030), text, fill=(40, 40, 40), font=text_font)
    draw.text((date_x, 1120), date, fill=(120, 120, 120), font=date_font)

    # 軽い影
    shadow = frame.filter(ImageFilter.GaussianBlur(8))
    final = Image.new("RGB", (1040, 1340), "#e5e3df")
    final.paste(shadow, (20, 20))
    final.paste(frame, (0, 0))

    final.save("/tmp/output.jpg", quality=95)

    url = f"{BASE_URL}/output.jpg?v={int(time.time())}"

    line_bot_api.reply_message(
        event.reply_token,
        ImageSendMessage(
            original_content_url=url,
            preview_image_url=url
        )
    )
