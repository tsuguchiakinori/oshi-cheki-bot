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


def load_font(size):
    try:
        return ImageFont.truetype("makiirclehand.ttf", size)
    except Exception:
        return ImageFont.load_default()


def fit_text(draw, text, max_width, start_size=74, min_size=34):
    size = start_size
    while size >= min_size:
        font = load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            return font
        size -= 4
    return load_font(min_size)


def apply_cheki_filter(img):
    img = ImageEnhance.Color(img).enhance(0.86)
    img = ImageEnhance.Contrast(img).enhance(0.94)
    img = ImageEnhance.Brightness(img).enhance(1.06)

    overlay = Image.new("RGB", img.size, (255, 246, 230))
    img = Image.blend(img, overlay, 0.10)

    noise = Image.new("RGB", img.size)
    pixels = noise.load()
    for y in range(img.size[1]):
        for x in range(img.size[0]):
            v = random.randint(235, 255)
            pixels[x, y] = (v, v, v)

    img = Image.blend(img, noise, 0.035)
    img = img.filter(ImageFilter.SMOOTH_MORE)

    return img


@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()

    if msg.startswith("テキスト"):
        text = msg.replace("テキスト", "", 1).strip()
        user_texts[user_id] = text or "My Oshi"
        reply = f"文字を設定したで📸\n「{user_texts[user_id]}」"

    elif msg.startswith("日付"):
        date_text = msg.replace("日付", "", 1).strip()
        user_dates[user_id] = date_text or ""
        reply = f"日付を設定したで📅\n「{user_dates[user_id]}」"

    elif "チェキ" in msg:
        reply = "① テキスト 好きな文字\n② 日付 2026.05.03\n③ 画像送信\nの順で送ってね📸"

    else:
        user_texts[user_id] = msg
        reply = f"文字を設定したで📸\n「{msg}」\n必要なら「日付 2026.05.03」も送ってね"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    cheki_text = user_texts.get(user_id, "My Oshi")
    date_text = user_dates.get(user_id, "")

    message_content = line_bot_api.get_message_content(event.message.id)

    with open("/tmp/input.jpg", "wb") as f:
        for chunk in message_content.iter_content():
            f.write(chunk)

    img = Image.open("/tmp/input.jpg").convert("RGB")

    w, h = img.size
    size = min(w, h)
    left = (w - size) // 2
    top = (h - size) // 2
    img = img.crop((left, top, left + size, top + size))
    img = img.resize((760, 760))
    img = apply_cheki_filter(img)

    # 背景＋影
    bg = Image.new("RGB", (980, 1260), (232, 232, 228))
    shadow = Image.new("RGB", (900, 1160), (205, 205, 200))
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))
    bg.paste(shadow, (54, 54))

    # チェキ本体
    frame = Image.new("RGB", (900, 1160), (252, 250, 245))
    frame.paste(img, (70, 70))

    draw = ImageDraw.Draw(frame)

    main_font = fit_text(draw, cheki_text, max_width=760, start_size=74, min_size=38)
    bbox = draw.textbbox((0, 0), cheki_text, font=main_font)
    text_width = bbox[2] - bbox[0]
    x = (900 - text_width) // 2
    y = 865

    draw.text((x + 1, y + 1), cheki_text, fill=(210, 205, 198), font=main_font)
    draw.text((x, y), cheki_text, fill=(35, 35, 35), font=main_font)

    if date_text:
        date_font = load_font(38)
        bbox = draw.textbbox((0, 0), date_text, font=date_font)
        date_width = bbox[2] - bbox[0]
        date_x = (900 - date_width) // 2
        date_y = 970
        draw.text((date_x, date_y), date_text, fill=(95, 95, 90), font=date_font)

    bg.paste(frame, (40, 40))
    bg.save("/tmp/output.jpg", quality=95)

    image_url = f"{BASE_URL}/output.jpg?v={int(time.time())}"

    line_bot_api.reply_message(
        event.reply_token,
        ImageSendMessage(
            original_content_url=image_url,
            preview_image_url=image_url
        )
    )
